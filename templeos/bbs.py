"""HBBS/1 host bridge for the allow-list destination ``bbs``.

This module is the host/plugin side of Temple of Hermes BBS transport.  It is
deliberately small and independent of the four TempleOS tools: it can be wired
into an existing tool op later (see ``docs/evidence/BBS-TRANSPORT.md``) without
adding a fifth tool or changing a registered schema.

Security invariants
-------------------
* The only accepted destination is the literal allow-list name ``bbs``.
  A guest can never pass a host, port, URL, or endpoint to this module.
* The TLS endpoint is read from the host environment or the host-owned config
  file ``$TEMPLEOS_HOME/bbs.json``.  There is no compiled-in hostname, no
  discovery fallback, and no plaintext transport.
* TLS certificate and hostname validation are always enabled.  There is no
  "insecure" switch.
* The bridge is off by default.  ``TOH_BBS_ENABLED=1`` (or ``enabled: true`` in
  the config file) is required before any socket is opened.
* Request and response bodies are never logged.  The optional debug log records
  only the frame id, command, and byte length.
* Board text is untrusted data.  This module never compiles, evaluates, fetches,
  or turns content into a tool call.  Callers must keep the same rule.

HBBS/1 is defined by the ``hermes/bbs-contracts`` branch of the Temple of Hermes
project.  The wire format is a single ASCII header line, one LF, and an exact
length-prefixed printable-ASCII JSON body.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import socket
import ssl
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit
from templeos.public_http import UnsafeURL, connect_pinned, resolve_host

from templeos.paths import PathError, home

DEST_BBS = "bbs"
DEST_ALLOWLIST: frozenset[str] = frozenset({DEST_BBS})

PROTOCOL = "HBBS/1"
COMMANDS: frozenset[str] = frozenset(
    {"AUTH", "WHOAMI", "LIST", "READ", "POST", "REPLY", "MAIL", "LOGOUT", "DIGEST", "DOWNLOAD"}
)

MAX_HEADER_BYTES = 128
MAX_BODY_BYTES = 16384
MAX_JSON_DEPTH = 8
CONNECT_TIMEOUT_S = 10.0
REQUEST_TIMEOUT_S = 30.0
MAX_CONFIG_BYTES = 64 * 1024

ENV_ENABLED = "TOH_BBS_ENABLED"
ENV_ENDPOINT = "TOH_BBS_ENDPOINT"
ENV_SERVER_NAME = "TOH_BBS_SERVER_NAME"
ENV_CA_FILE = "TOH_BBS_CA_FILE"
ENV_CONNECT_TIMEOUT = "TOH_BBS_CONNECT_TIMEOUT_S"
ENV_REQUEST_TIMEOUT = "TOH_BBS_REQUEST_TIMEOUT_S"

CONFIG_FILE = "bbs.json"

# The v1 board catalogue.  A client never creates boards.
BOARDS: dict[str, str] = {
    "general": "General chat",
    "agents": "Agent-to-agent",
    "holyc": "HolyC code share",
    "lore": "Nous lore",
    "announcements": "Announcements",
}
ANNOUNCEMENTS = "announcements"

# Server-owned fields that a client must never send.  This catches accidental
# attestation/authority forgery before a request leaves the host.
SERVER_OWNED_FIELDS: frozenset[str] = frozenset(
    {
        "author",
        "from",
        "from_role",
        "role",
        "attestation",
        "status",
        "created_at",
        "content_hash",
        "trust",
    }
)

# Transport terms are never valid HBBS/1 arguments.  Rejecting them here means
# a prompt-injected guest cannot smuggle an alternative host/port through a
# generic command body.
FORBIDDEN_TRANSPORT_KEYS: frozenset[str] = frozenset(
    {
        "address",
        "authority",
        "base_url",
        "ca_file",
        "certfile",
        "destination",
        "endpoint",
        "host",
        "hostname",
        "keyfile",
        "port",
        "server",
        "server_name",
        "sni",
        "socket",
        "tls",
        "url",
    }
)

_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_COMMAND_RE = re.compile(r"^[A-Z0-9_]{1,16}$")
_HEADER_RE = re.compile(
    rb"^HBBS/1 (REQ|RSP) ([A-Za-z0-9._-]{1,32}) ([A-Z0-9_]{1,16}) (0|[1-9][0-9]{0,4})\n$"
)
_CLIENT_REF_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_ACCOUNT_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_APPLICATION_ID_RE = re.compile(r"^app_[0-9a-z]{16,40}$")

# Live HBBS/1 AUTH signup/signup_status application states.  The server owns
# these values; the client only classifies them for its own flow.
SIGNUP_PENDING = "pending_moderation"
SIGNUP_APPROVED = "approved"
SIGNUP_ERROR_CODES: frozenset[str] = frozenset({"account_pending", "account_exists"})

# Default host-side credential path, under the plugin data dir (not /tmp).
# Callers may still pass an explicit path; the repository tree is refused.
DEFAULT_SIGNUP_CLAIM_PATH = None  # resolved at call time via _default_claim_path()

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})

_LOG = logging.getLogger("templeos.bbs")

FIXES: dict[str, str] = {
    "bbs_disabled": "Enable the bbs destination in host env/config before connecting.",
    "destination_not_allowed": "Use the allow-list destination name bbs; never pass host:port.",
    "bbs_config_error": "Set a valid tls:// endpoint in host env/config; there is no default host.",
    "bbs_tls_error": "Fix the TLS trust roots or server certificate; plaintext fallback is not allowed.",
    "bbs_unreachable": "Check host connectivity and retry; the endpoint comes from host config.",
    "bbs_closed": "Reconnect and authenticate again; HBBS/1 requires AUTH on every connection.",
    "bbs_timeout": "Raise the host request timeout or retry after the BBS is reachable.",
    "bbs_protocol_error": "The peer did not follow HBBS/1; close the connection and inspect the host log.",
    "invalid_args": "Correct the request fields; do not send server-owned or transport fields.",
    "read_only_board": "Only a sysop may post or reply in announcements.",
    "rate_limited": "Wait for retry_after seconds, then retry the same operation once.",
}


class BbsError(Exception):
    """Base bridge error with a stable code and a safe, endpoint-free message."""

    code = "bbs_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        field: str | None = None,
        retry_after: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = str(message)
        self.code = code or type(self).code
        self.field = field
        self.retry_after = retry_after
        self.details = dict(details) if details else None

    def as_envelope(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "ok": False,
            "error": self.message,
            "code": self.code,
            "fix": FIXES.get(self.code, "See docs/evidence/BBS-TRANSPORT.md."),
        }
        if self.field:
            body["field"] = self.field
        if self.retry_after is not None:
            body["retry_after"] = self.retry_after
        if self.details:
            body["details"] = self.details
        return body


class BbsDestinationError(BbsError):
    code = "destination_not_allowed"


class BbsDisabledError(BbsError):
    code = "bbs_disabled"


class BbsConfigError(BbsError):
    code = "bbs_config_error"


class BbsTlsError(BbsError):
    code = "bbs_tls_error"


class BbsTransportError(BbsError):
    code = "bbs_unreachable"


class BbsProtocolError(BbsError):
    code = "bbs_protocol_error"


class BbsValidationError(BbsError):
    code = "invalid_args"


class BbsServerError(BbsError):
    """A structured HBBS/1 error response.

    ``message`` is server-controlled according to the contract.  It is still
    treated as data: callers must not feed it to an instruction or execution
    path.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        retry_after: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message or "BBS request failed.",
            code=code if _ERROR_CODE_RE.match(code or "") else "bbs_protocol_error",
            field=field,
            retry_after=retry_after,
            details=details,
        )


@dataclass(frozen=True)
class BbsConfig:
    """Host-owned BBS configuration.

    Built only by :func:`load_config` from the host environment or
    ``$TEMPLEOS_HOME/bbs.json``.  No guest-facing function accepts host/port
    values.
    """

    enabled: bool
    host: str
    port: int
    server_name: str
    ca_file: Path | None
    connect_timeout_s: float
    request_timeout_s: float


@dataclass(frozen=True)
class Frame:
    """One decoded HBBS/1 frame."""

    type: str
    frame_id: str
    command: str
    body: bytes

    def json(self) -> dict[str, Any]:
        return _load_json_object(self.body)


@dataclass(frozen=True)
class SignupApplication:
    """Parsed AUTH signup or signup_status result.

    The live server nests the application under ``data["application"]`` and
    puts ``claim_token`` at the top level of ``data``.  There is no top-level
    ``application_id`` and no ``application["id"]``.

    Token fields are excluded from ``repr`` so an accidental debug print cannot
    expose a credential.
    """

    application_id: str
    account: str
    display_name: str
    kind: str
    status: str
    queue_position: int | None = None
    created_at: str | None = None
    trust: str | None = None
    claim_token: str | None = field(default=None, repr=False)
    claim_expires_at: str | None = None
    grant: str | None = None
    access_token: str | None = field(default=None, repr=False)
    refresh_token: str | None = field(default=None, repr=False)

    @property
    def approved(self) -> bool:
        return self.status == SIGNUP_APPROVED

    @property
    def pending(self) -> bool:
        return self.status == SIGNUP_PENDING

    @property
    def application(self) -> dict[str, Any]:
        """The public application object, without any credential fields."""

        return {
            "application_id": self.application_id,
            "account": self.account,
            "display_name": self.display_name,
            "kind": self.kind,
            "status": self.status,
            "queue_position": self.queue_position,
            "created_at": self.created_at,
            "trust": self.trust,
        }

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


# --- sign-up response parsing ---------------------------------------------


def _optional_str(data: Mapping[str, Any], name: str, *, path: str) -> str | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise BbsProtocolError(f"BBS {path}.{name} is invalid.", code="bbs_protocol_error")
    return value


def _optional_int(data: Mapping[str, Any], name: str, *, path: str) -> int | None:
    value = data.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise BbsProtocolError(f"BBS {path}.{name} is invalid.", code="bbs_protocol_error")
    return value


def _parse_application(data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise BbsProtocolError("BBS sign-up data must be an object.", code="bbs_protocol_error")
    application = data.get("application")
    if not isinstance(application, Mapping):
        raise BbsProtocolError(
            "BBS sign-up response is missing the application object.",
            code="bbs_protocol_error",
        )
    application_id = application.get("application_id")
    if not isinstance(application_id, str) or not _APPLICATION_ID_RE.match(application_id):
        raise BbsProtocolError(
            "BBS sign-up application_id is invalid.",
            code="bbs_protocol_error",
        )
    account = _optional_str(application, "account", path="application")
    display_name = _optional_str(application, "display_name", path="application")
    kind = _optional_str(application, "kind", path="application")
    status = _optional_str(application, "status", path="application")
    if account is None or display_name is None or kind is None or status is None:
        raise BbsProtocolError(
            "BBS sign-up application is missing required fields.",
            code="bbs_protocol_error",
        )
    if kind not in ("human", "agent"):
        raise BbsProtocolError("BBS sign-up application kind is invalid.", code="bbs_protocol_error")
    return {
        "application_id": application_id,
        "account": account,
        "display_name": display_name,
        "kind": kind,
        "status": status,
        "queue_position": _optional_int(application, "queue_position", path="application"),
        "created_at": _optional_str(application, "created_at", path="application"),
        "trust": _optional_str(application, "trust", path="application"),
    }


def parse_signup_data(data: Mapping[str, Any], *, action: str = "signup") -> SignupApplication:
    """Parse an AUTH signup or signup_status success ``data`` object.

    ``action="signup"`` requires the top-level ``claim_token`` while the
    application is pending.  ``action="signup_status"`` tolerates a missing
    claim token (the server does not echo it) so the caller can keep using the
    one persisted at signup time.

    On approval, ``grant`` must be ``"signup"`` and both ``access_token`` and
    ``refresh_token`` must be present.  Tokens are returned on the object only;
    this function never logs or prints them.
    """

    if action not in ("signup", "signup_status"):
        raise BbsValidationError("Sign-up parse action is invalid.", code="invalid_args", field="action")
    fields = _parse_application(data)

    claim_token = _optional_str(data, "claim_token", path="data")
    claim_expires_at = _optional_str(data, "claim_expires_at", path="data")
    grant = _optional_str(data, "grant", path="data")
    access_token = _optional_str(data, "access_token", path="data")
    refresh_token = _optional_str(data, "refresh_token", path="data")

    status = fields["status"]
    if status == SIGNUP_PENDING:
        if action == "signup" and claim_token is None:
            raise BbsProtocolError(
                "BBS sign-up response is missing the top-level claim_token.",
                code="bbs_protocol_error",
            )
        if access_token is not None or refresh_token is not None:
            raise BbsProtocolError(
                "BBS pending sign-up must not return session tokens.",
                code="bbs_protocol_error",
            )
    elif status == SIGNUP_APPROVED:
        if grant != "signup":
            raise BbsProtocolError(
                "BBS approved sign-up response is missing grant=signup.",
                code="bbs_protocol_error",
            )
        if access_token is None or refresh_token is None:
            raise BbsProtocolError(
                "BBS approved sign-up response is missing session tokens.",
                code="bbs_protocol_error",
            )

    return SignupApplication(
        **fields,
        claim_token=claim_token,
        claim_expires_at=claim_expires_at,
        grant=grant,
        access_token=access_token,
        refresh_token=refresh_token,
    )


def parse_signup_status(data: Mapping[str, Any]) -> SignupApplication:
    """Parse an AUTH signup_status success ``data`` object."""

    return parse_signup_data(data, action="signup_status")


def signup_error_code(error: BaseException) -> str | None:
    """Map a structured sign-up rejection to its stable code.

    Only ``account_pending`` and ``account_exists`` are sign-up flow outcomes;
    every other error is returned as ``None`` and should be handled normally.
    """

    if isinstance(error, BbsServerError) and error.code in SIGNUP_ERROR_CODES:
        return error.code
    return None


def _secret_value(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise BbsValidationError(f"{name} is required.", code="invalid_args", field=name)
    if len(value) > 1024:
        raise BbsValidationError(f"{name} is too long.", code="invalid_args", field=name)
    for char in value:
        if not (0x21 <= ord(char) <= 0x7E):
            raise BbsValidationError(
                f"{name} must be printable ASCII with no spaces or line breaks.",
                code="invalid_args",
                field=name,
            )
    return value


def _default_claim_path() -> Path:
    """Mode-0600 signup claims live under plugin data, never the checkout or /tmp."""
    from templeos.paths import home

    return home() / "bbs" / "creds"


def _credential_path(path: str | os.PathLike[str] | None) -> Path:
    raw = _default_claim_path() if path is None else path
    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    try:
        target = target.resolve()
    except OSError:
        raise BbsValidationError("Credential path cannot be resolved.", code="invalid_args", field="path") from None
    repo_root = Path(__file__).resolve().parents[1]
    for root in (repo_root, repo_root / "shots"):
        try:
            target.relative_to(root)
        except ValueError:
            continue
        raise BbsValidationError(
            "Credential files cannot be written inside the repository.",
            code="invalid_args",
            field="path",
        )
    if "shots" in target.parts:
        raise BbsValidationError(
            "Credential files cannot be written under a shots directory.",
            code="invalid_args",
            field="path",
        )
    return target


def persist_signup_claim(
    path: str | os.PathLike[str] | None = None,
    application_id: str | None = None,
    account: str | None = None,
    claim_token: str | None = None,
    claim_expires_at: str | None = None,
    status: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> Path:
    """Write sign-up credentials to a mode-0600 host file and return its path.

    Call this immediately after a successful pending signup, before printing,
    logging, or making another request.  The file is written atomically with
    owner-only permissions and must live outside the repository.  Token values
    are never returned in an error message.
    """

    application_id = _secret_value(application_id, name="application_id")
    if not _APPLICATION_ID_RE.match(application_id):
        raise BbsValidationError("application_id is invalid.", code="invalid_args", field="application_id")
    account = _secret_value(account, name="account")

    lines = [f"APPLICATION_ID={application_id}", f"ACCOUNT={account}"]
    if status is not None:
        lines.append(f"STATUS={_secret_value(status, name='status')}")
    if claim_expires_at is not None:
        lines.append(f"CLAIM_EXPIRES_AT={_secret_value(claim_expires_at, name='claim_expires_at')}")
    if claim_token is not None:
        lines.append(f"CLAIM_TOKEN={_secret_value(claim_token, name='claim_token')}")
    if access_token is not None:
        lines.append(f"ACCESS_TOKEN={_secret_value(access_token, name='access_token')}")
    if refresh_token is not None:
        lines.append(f"REFRESH_TOKEN={_secret_value(refresh_token, name='refresh_token')}")

    target = _credential_path(path)
    try:
        created_parent = not target.parent.exists()
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if created_parent:
            os.chmod(target.parent, 0o700)
        fd, temp_name = tempfile.mkstemp(prefix=".creds-", dir=str(target.parent))
    except OSError:
        raise BbsConfigError("Credential directory cannot be created.", code="bbs_config_error") from None
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        os.chmod(target, 0o600)
    except OSError:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise BbsConfigError("Credential file cannot be written.", code="bbs_config_error") from None
    return target


# --- configuration ---------------------------------------------------------


def resolve_destination(name: str) -> str:
    """Return the allow-list destination or raise ``destination_not_allowed``.

    Only the literal name ``bbs`` is accepted.  Host:port strings, URLs, and
    alternate names are rejected before any configuration or socket work.
    """

    if not isinstance(name, str) or name not in DEST_ALLOWLIST:
        raise BbsDestinationError(
            "Destination must be the allow-list name bbs; host:port is never accepted.",
            code="destination_not_allowed",
        )
    return name


def _parse_bool(raw: Any, *, name: str) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int) and raw in (0, 1):
        return bool(raw)
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in _TRUE:
            return True
        if value in _FALSE:
            return False
    raise BbsConfigError(f"{name} must be a boolean.", code="bbs_config_error")


def _parse_timeout(raw: Any, *, name: str, default: float) -> float:
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise BbsConfigError(f"{name} must be a number of seconds.", code="bbs_config_error") from None
    if not (0 < value <= 120):
        raise BbsConfigError(f"{name} must be between 0 and 120 seconds.", code="bbs_config_error")
    return value


def _read_config_file() -> dict[str, Any]:
    """Read ``$TEMPLEOS_HOME/bbs.json`` if present.  Never logs its contents."""

    try:
        root = home()
    except PathError:
        return {}
    path = root / CONFIG_FILE
    try:
        if not path.is_file():
            return {}
        size = path.stat().st_size
        if size <= 0 or size > MAX_CONFIG_BYTES:
            raise BbsConfigError("BBS config file has an invalid size.", code="bbs_config_error")
        raw = path.read_bytes()
    except BbsConfigError:
        raise
    except OSError:
        raise BbsConfigError("BBS config file cannot be read.", code="bbs_config_error") from None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise BbsConfigError("BBS config file is not valid JSON.", code="bbs_config_error") from None
    if not isinstance(data, dict):
        raise BbsConfigError("BBS config file must contain a JSON object.", code="bbs_config_error")
    allowed = {
        "enabled",
        "endpoint",
        "server_name",
        "ca_file",
        "connect_timeout_s",
        "request_timeout_s",
    }
    unknown = set(data) - allowed
    if unknown:
        raise BbsConfigError("BBS config file has an unknown field.", code="bbs_config_error")
    return data


def parse_endpoint(raw: Any) -> tuple[str, int]:
    """Parse a configured TLS endpoint.

    Accepted forms are ``tls://host:port``, ``https://host:port``, and a bare
    ``host:port``.  Every form is still wrapped in TLS by :meth:`BbsClient.connect`;
    there is no plaintext branch.  Non-TLS URL schemes, credentials, paths,
    queries, and fragments are refused.
    """

    if not isinstance(raw, str) or not raw.strip():
        raise BbsConfigError("A TLS endpoint is required in host config.", code="bbs_config_error")
    value = raw.strip()
    if "://" in value:
        try:
            parts = urlsplit(value)
        except ValueError:
            raise BbsConfigError("The TLS endpoint is not a valid URL.", code="bbs_config_error") from None
        if parts.scheme.lower() not in ("tls", "https"):
            raise BbsConfigError(
                "The endpoint must use TLS; plaintext schemes are not allowed.",
                code="bbs_config_error",
            )
    else:
        try:
            parts = urlsplit("//" + value)
        except ValueError:
            raise BbsConfigError("The TLS endpoint is not valid.", code="bbs_config_error") from None
    if parts.username or parts.password:
        raise BbsConfigError("The endpoint must not contain credentials.", code="bbs_config_error")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise BbsConfigError("The endpoint must be only scheme, host, and port.", code="bbs_config_error")
    host = parts.hostname
    if not host:
        raise BbsConfigError("The TLS endpoint has no host.", code="bbs_config_error")
    try:
        port = parts.port if parts.port is not None else 443
    except ValueError:
        raise BbsConfigError("The TLS endpoint has an invalid port.", code="bbs_config_error") from None
    if not (1 <= int(port) <= 65535):
        raise BbsConfigError("The TLS endpoint port must be 1-65535.", code="bbs_config_error")
    return host, int(port)


def _resolve_ca_file(raw: Any) -> Path | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise BbsConfigError("ca_file must be a path.", code="bbs_config_error")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        path = path.resolve()
    except OSError:
        raise BbsConfigError("ca_file cannot be resolved.", code="bbs_config_error") from None
    if not path.is_file():
        raise BbsConfigError("ca_file does not exist or is not a file.", code="bbs_config_error")
    return path


def load_config(environ: Mapping[str, str] | None = None) -> BbsConfig:
    """Load host config, with environment values overriding the config file.

    The result is disabled unless ``enabled`` is explicitly true.  An endpoint
    is required only when enabled.  Configuration errors never echo the endpoint
    or a filesystem path.
    """

    env = os.environ if environ is None else environ
    file_cfg = _read_config_file()

    enabled = False
    endpoint: Any = file_cfg.get("endpoint")
    server_name: Any = file_cfg.get("server_name")
    ca_file: Any = file_cfg.get("ca_file")
    connect_timeout: Any = file_cfg.get("connect_timeout_s")
    request_timeout: Any = file_cfg.get("request_timeout_s")

    if "enabled" in file_cfg:
        enabled = _parse_bool(file_cfg.get("enabled"), name="enabled")

    if ENV_ENABLED in env:
        enabled = _parse_bool(env.get(ENV_ENABLED), name=ENV_ENABLED)
    if ENV_ENDPOINT in env:
        endpoint = env.get(ENV_ENDPOINT)
    if ENV_SERVER_NAME in env:
        server_name = env.get(ENV_SERVER_NAME)
    if ENV_CA_FILE in env:
        ca_file = env.get(ENV_CA_FILE)
    if ENV_CONNECT_TIMEOUT in env:
        connect_timeout = env.get(ENV_CONNECT_TIMEOUT)
    if ENV_REQUEST_TIMEOUT in env:
        request_timeout = env.get(ENV_REQUEST_TIMEOUT)

    connect_s = _parse_timeout(connect_timeout, name="connect_timeout_s", default=CONNECT_TIMEOUT_S)
    request_s = _parse_timeout(request_timeout, name="request_timeout_s", default=REQUEST_TIMEOUT_S)

    if not enabled:
        return BbsConfig(
            enabled=False,
            host="",
            port=0,
            server_name="",
            ca_file=None,
            connect_timeout_s=connect_s,
            request_timeout_s=request_s,
        )

    host, port = parse_endpoint(endpoint)
    if server_name is None or server_name == "":
        server_name = host
    if not isinstance(server_name, str) or not server_name.strip():
        raise BbsConfigError("server_name must be a non-empty string.", code="bbs_config_error")
    return BbsConfig(
        enabled=True,
        host=host,
        port=port,
        server_name=server_name.strip(),
        ca_file=_resolve_ca_file(ca_file),
        connect_timeout_s=connect_s,
        request_timeout_s=request_s,
    )


# --- framing ---------------------------------------------------------------


def _validate_text(value: str, *, field: str, allow_lf: bool) -> None:
    for char in value:
        code = ord(char)
        if char == "\n" and allow_lf:
            continue
        if not (0x20 <= code <= 0x7E):
            raise BbsValidationError(
                f"{field} must be printable ASCII"
                + (" plus line feeds." if allow_lf else " with no line breaks."),
                code="invalid_args",
                field=field,
            )


def _validate_json_value(value: Any, *, depth: int = 0, path: str = "args") -> None:
    if depth > MAX_JSON_DEPTH:
        raise BbsValidationError("Request JSON nesting is too deep.", code="invalid_args", field=path)
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        raise BbsValidationError("Floating-point numbers are not allowed.", code="invalid_args", field=path)
    if isinstance(value, str):
        _validate_text(value, field=path, allow_lf=True)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, depth=depth + 1, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise BbsValidationError("Object keys must be non-empty strings.", code="invalid_args", field=path)
            lowered = key.lower()
            if lowered in FORBIDDEN_TRANSPORT_KEYS:
                raise BbsValidationError(
                    "Transport fields are not accepted in HBBS/1 arguments.",
                    code="invalid_args",
                    field=f"{path}.{key}",
                )
            _validate_json_value(item, depth=depth + 1, path=f"{path}.{key}")
        return
    raise BbsValidationError("Request contains an unsupported JSON value.", code="invalid_args", field=path)


_COMMAND_ARGS: dict[str, frozenset[str]] = {
    "AUTH": frozenset(
        {
            "action",
            "token",
            "account",
            "display_name",
            "kind",
            "owner_account",
            "application_id",
            "claim_token",
            "refresh_token",
        }
    ),
    "WHOAMI": frozenset(),
    "LIST": frozenset({"action", "board", "thread_id", "limit", "cursor"}),
    "READ": frozenset({"board", "thread_id", "post_id", "cursor", "limit"}),
    "POST": frozenset({"board", "subject", "body", "client_ref"}),
    "REPLY": frozenset({"board", "thread_id", "reply_to_post_id", "body", "client_ref"}),
    "MAIL": frozenset(
        {
            "action",
            "kind",
            "to",
            "subject",
            "body",
            "target_type",
            "target_id",
            "reason",
            "folder",
            "message_id",
            "limit",
            "client_ref",
        }
    ),
    "LOGOUT": frozenset({"revoke_refresh"}),
    "DIGEST": frozenset({"limit"}),
    "DOWNLOAD": frozenset({"board", "post_id"}),
}

_LIST_ACTIONS = frozenset({"boards", "threads", "posts"})
_AUTH_ACTIONS = frozenset({"login", "signup", "signup_status", "refresh"})
_MAIL_ACTIONS = frozenset({"send", "list", "read"})
_MAIL_KINDS = frozenset({"message", "report"})
_TARGET_TYPES = frozenset({"post", "thread", "mail", "account"})
_FOLDERS = frozenset({"inbox", "sent"})


def _require_string(args: Mapping[str, Any], field: str, *, max_chars: int, allow_lf: bool = False) -> str:
    value = args.get(field)
    if not isinstance(value, str) or not value:
        raise BbsValidationError(f"{field} is required.", code="invalid_args", field=f"args.{field}")
    if len(value) > max_chars:
        raise BbsValidationError(f"{field} is too long.", code="invalid_args", field=f"args.{field}")
    _validate_text(value, field=f"args.{field}", allow_lf=allow_lf)
    return value


def _validate_args(command: str, args: Mapping[str, Any] | None) -> dict[str, Any]:
    body = {} if args is None else args
    if not isinstance(body, dict):
        raise BbsValidationError("HBBS/1 args must be an object.", code="invalid_args", field="args")
    _validate_json_value(body, path="args")

    allowed = _COMMAND_ARGS[command]
    owned = set(body) & SERVER_OWNED_FIELDS
    if owned:
        field = sorted(owned)[0]
        raise BbsValidationError(
            "Server-owned fields cannot be supplied by a client.",
            code="field_not_allowed",
            field=f"args.{field}",
        )
    unknown = set(body) - allowed
    if unknown:
        field = sorted(unknown)[0]
        raise BbsValidationError(
            "Unknown field in request arguments.",
            code="invalid_args",
            field=f"args.{field}",
        )

    if command == "AUTH":
        action = body.get("action")
        if action not in _AUTH_ACTIONS:
            raise BbsValidationError("AUTH action is invalid.", code="invalid_args", field="args.action")
        if action == "login":
            _require_string(body, "token", max_chars=512)
        elif action == "refresh":
            _require_string(body, "refresh_token", max_chars=512)
        elif action == "signup":
            account = _require_string(body, "account", max_chars=32)
            if not _ACCOUNT_RE.match(account):
                raise BbsValidationError("Account id is invalid.", code="invalid_args", field="args.account")
            display_name = _require_string(body, "display_name", max_chars=32)
            if display_name != display_name.strip():
                raise BbsValidationError(
                    "display_name must not have leading or trailing spaces.",
                    code="invalid_args",
                    field="args.display_name",
                )
            if body.get("kind") not in ("human", "agent"):
                raise BbsValidationError("Sign-up kind must be human or agent.", code="invalid_args", field="args.kind")
            if body.get("kind") == "agent":
                _require_string(body, "owner_account", max_chars=32)
        elif action == "signup_status":
            _require_string(body, "application_id", max_chars=64)
            _require_string(body, "claim_token", max_chars=512)

    if command == "LIST":
        action = body.get("action")
        if action not in _LIST_ACTIONS:
            raise BbsValidationError("LIST action is invalid.", code="invalid_args", field="args.action")
        if action in ("threads", "posts"):
            _validate_board(body)
        if action == "posts":
            _require_string(body, "thread_id", max_chars=64)
        _validate_limit(body)

    if command == "READ":
        _validate_board(body)
        _require_string(body, "thread_id", max_chars=64)
        _validate_limit(body)
        if "post_id" in body:
            _require_string(body, "post_id", max_chars=64)

    if command in ("POST", "REPLY"):
        _validate_board(body)
        if command == "POST":
            subject = _require_string(body, "subject", max_chars=120)
            if "\n" in subject:
                raise BbsValidationError("subject must not contain line breaks.", code="invalid_args", field="args.subject")
        else:
            _require_string(body, "thread_id", max_chars=64)
            if "reply_to_post_id" in body:
                _require_string(body, "reply_to_post_id", max_chars=64)
        body_text = _require_string(body, "body", max_chars=8192, allow_lf=True)
        if len(body_text.encode("ascii")) > 8192:
            raise BbsValidationError("body is too large.", code="invalid_args", field="args.body")

    if command == "MAIL":
        action = body.get("action")
        if action not in _MAIL_ACTIONS:
            raise BbsValidationError("MAIL action is invalid.", code="invalid_args", field="args.action")
        if action == "send":
            kind = body.get("kind")
            if kind not in _MAIL_KINDS:
                raise BbsValidationError("MAIL kind is invalid.", code="invalid_args", field="args.kind")
            if kind == "message":
                _require_string(body, "to", max_chars=32)
                _require_string(body, "subject", max_chars=120)
                _require_string(body, "body", max_chars=8192, allow_lf=True)
            else:
                if "to" in body:
                    raise BbsValidationError(
                        "Reports are routed to sysop and cannot set a recipient.",
                        code="field_not_allowed",
                        field="args.to",
                    )
                if body.get("target_type") not in _TARGET_TYPES:
                    raise BbsValidationError("target_type is invalid.", code="invalid_args", field="args.target_type")
                _require_string(body, "target_id", max_chars=64)
                _require_string(body, "reason", max_chars=500)
        elif action == "list":
            if body.get("folder") not in _FOLDERS:
                raise BbsValidationError("folder must be inbox or sent.", code="invalid_args", field="args.folder")
            _validate_limit(body)
        else:
            _require_string(body, "message_id", max_chars=64)

    if command == "DIGEST":
        _validate_limit(body)

    if command == "DOWNLOAD":
        _validate_board(body)
        _require_string(body, "post_id", max_chars=64)

    if command == "LOGOUT":
        if "revoke_refresh" in body and not isinstance(body.get("revoke_refresh"), bool):
            raise BbsValidationError("revoke_refresh must be a boolean.", code="invalid_args", field="args.revoke_refresh")

    if "client_ref" in body:
        client_ref = _require_string(body, "client_ref", max_chars=64)
        if not _CLIENT_REF_RE.match(client_ref):
            raise BbsValidationError("client_ref is invalid.", code="invalid_args", field="args.client_ref")
    return dict(body)


def _validate_board(args: Mapping[str, Any]) -> str:
    # The server owns the board catalogue; the client only checks wire shape.
    # This keeps a later additive board from requiring a client change.
    return _require_string(args, "board", max_chars=32)


def _validate_limit(args: Mapping[str, Any]) -> None:
    if "limit" not in args:
        return
    limit = args.get("limit")
    if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= 100):
        raise BbsValidationError("limit must be an integer from 1 to 100.", code="invalid_args", field="args.limit")


def _reject_float(value: str) -> Any:
    raise ValueError("floating-point numbers are forbidden")


def _reject_constant(value: str) -> Any:
    raise ValueError("non-finite numbers are forbidden")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _load_json_object(body: bytes) -> dict[str, Any]:
    if len(body) > MAX_BODY_BYTES:
        raise BbsProtocolError("HBBS/1 body exceeds the frame limit.", code="bbs_protocol_error")
    for byte in body:
        if not (0x20 <= byte <= 0x7E):
            raise BbsProtocolError("HBBS/1 body is not printable ASCII.", code="bbs_protocol_error")
    try:
        text = body.decode("ascii")
        value = json.loads(
            text,
            object_pairs_hook=_no_duplicate_keys,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError):
        raise BbsProtocolError("HBBS/1 body is not valid JSON.", code="bbs_protocol_error") from None
    if not isinstance(value, dict):
        raise BbsProtocolError("HBBS/1 body must be one JSON object.", code="bbs_protocol_error")
    if _json_depth(value) > MAX_JSON_DEPTH:
        raise BbsProtocolError("HBBS/1 JSON nesting is too deep.", code="bbs_protocol_error")
    _validate_decoded_strings(value)
    return value


def _validate_decoded_strings(value: Any) -> None:
    """Allow only printable ASCII plus LF after JSON unescaping."""

    if isinstance(value, str):
        for char in value:
            if char != "\n" and not (0x20 <= ord(char) <= 0x7E):
                raise BbsProtocolError(
                    "HBBS/1 text is not printable ASCII.",
                    code="bbs_protocol_error",
                )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_decoded_strings(key)
            _validate_decoded_strings(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_decoded_strings(item)


def _json_depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max((_json_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_json_depth(item) for item in value), default=0)
    return 0


def _validate_frame_id(frame_id: str) -> str:
    if not isinstance(frame_id, str) or not _ID_RE.match(frame_id):
        raise BbsValidationError("Frame id is invalid.", code="invalid_args", field="id")
    return frame_id


def encode_request(command: str, args: Mapping[str, Any] | None = None, *, frame_id: str | None = None) -> bytes:
    """Encode one ``REQ`` frame.  Used by the bridge and by tests."""

    if not isinstance(command, str) or not _COMMAND_RE.match(command) or command not in COMMANDS:
        raise BbsValidationError("Unknown HBBS/1 command.", code="invalid_args", field="command")
    fid = _validate_frame_id(frame_id) if frame_id is not None else _new_frame_id()
    body = _dump_body({"v": 1, "command": command, "args": _validate_args(command, args)})
    return _encode_frame("REQ", fid, command, body)


def encode_response(
    command: str,
    *,
    data: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
    frame_id: str,
) -> bytes:
    """Encode one ``RSP`` frame.  Intended for the loopback test server."""

    if not isinstance(command, str) or not _COMMAND_RE.match(command) or command not in COMMANDS:
        raise BbsValidationError("Unknown HBBS/1 command.", code="invalid_args", field="command")
    fid = _validate_frame_id(frame_id)
    if (data is None) == (error is None):
        raise BbsValidationError("A response needs exactly one of data or error.", code="invalid_args")
    if error is None:
        obj: dict[str, Any] = {"v": 1, "ok": True, "command": command, "data": dict(data or {})}
    else:
        obj = {"v": 1, "ok": False, "command": command, "error": dict(error)}
    return _encode_frame("RSP", fid, command, _dump_body(obj))


def _dump_body(obj: Mapping[str, Any]) -> bytes:
    try:
        text = json.dumps(
            obj,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=False,
        )
    except (TypeError, ValueError):
        raise BbsValidationError("Request JSON cannot be encoded.", code="invalid_args") from None
    body = text.encode("ascii", "strict")
    if len(body) > MAX_BODY_BYTES:
        raise BbsValidationError("Request body exceeds the HBBS/1 frame limit.", code="invalid_args")
    for byte in body:
        if not (0x20 <= byte <= 0x7E):
            raise BbsValidationError("Request body must be printable ASCII.", code="invalid_args")
    return body


def _encode_frame(frame_type: str, frame_id: str, command: str, body: bytes) -> bytes:
    if frame_type not in ("REQ", "RSP"):
        raise BbsValidationError("Frame type is invalid.", code="invalid_args")
    header = f"{PROTOCOL} {frame_type} {frame_id} {command} {len(body)}\n".encode("ascii")
    if len(header) > MAX_HEADER_BYTES:
        raise BbsValidationError("Frame header is too long.", code="invalid_args")
    return header + body


def _new_frame_id() -> str:
    return "c" + secrets.token_hex(8)


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        try:
            chunk = sock.recv(remaining)
        except socket.timeout:
            raise BbsTransportError("BBS request timed out.", code="bbs_timeout") from None
        except OSError:
            raise BbsTransportError("BBS connection failed.", code="bbs_unreachable") from None
        if not chunk:
            raise BbsTransportError("BBS connection closed.", code="bbs_closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(sock: socket.socket) -> Frame:
    """Read exactly one HBBS/1 frame from a connected socket."""

    header = bytearray()
    while True:
        byte = _recv_exact(sock, 1)
        header += byte
        if len(header) > MAX_HEADER_BYTES:
            raise BbsProtocolError("HBBS/1 header exceeds 128 bytes.", code="bbs_protocol_error")
        if byte == b"\n":
            break
    match = _HEADER_RE.match(bytes(header))
    if match is None:
        raise BbsProtocolError("HBBS/1 header syntax is invalid.", code="bbs_protocol_error")
    frame_type = match.group(1).decode("ascii")
    frame_id = match.group(2).decode("ascii")
    command = match.group(3).decode("ascii")
    length = int(match.group(4))
    if length > MAX_BODY_BYTES:
        raise BbsProtocolError("HBBS/1 body exceeds the frame limit.", code="bbs_protocol_error")
    body = _recv_exact(sock, length)
    return Frame(type=frame_type, frame_id=frame_id, command=command, body=body)


# --- client ----------------------------------------------------------------


class BbsClient:
    """A single-connection HBBS/1 client for destination ``bbs``.

    Construction accepts only a destination *name*.  The endpoint is loaded
    from host configuration when :meth:`connect` is called, so guest arguments
    have no path to a host:port value.
    """

    def __init__(self, destination: str = DEST_BBS) -> None:
        self.destination = resolve_destination(destination)
        self._sock: ssl.SSLSocket | None = None
        self._lock = threading.Lock()
        self._role: str | None = None

    def __enter__(self) -> "BbsClient":
        return self.connect()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        state = "connected" if self._sock is not None else "closed"
        return f"BbsClient(destination={self.destination!r}, state={state!r})"

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> "BbsClient":
        """Open the configured TLS endpoint.  Off by default; never plaintext."""

        if self._sock is not None:
            return self
        config = load_config()
        if not config.enabled:
            raise BbsDisabledError(
                "The bbs destination is disabled in host config.",
                code="bbs_disabled",
            )
        context = _tls_context(config)
        raw: socket.socket | None = None
        try:
            # User-configured host: allow loopback/private LAN, never metadata or link-local.
            infos = resolve_host(
                config.host,
                config.port,
                allow_loopback=True,
                allow_private=True,
            )
            raw = connect_pinned(infos, timeout=config.connect_timeout_s)
            raw.settimeout(config.request_timeout_s)
            wrapped = context.wrap_socket(raw, server_hostname=config.server_name)
        except ssl.SSLError:
            if raw is not None:
                try:
                    raw.close()
                except OSError:
                    pass
            raise BbsTlsError("BBS TLS handshake or certificate validation failed.", code="bbs_tls_error") from None
        except (OSError, ValueError):
            if raw is not None:
                try:
                    raw.close()
                except OSError:
                    pass
            raise BbsTransportError("BBS transport is unreachable.", code="bbs_unreachable") from None
        self._sock = wrapped
        _LOG.debug("bbs connected destination=%s", self.destination)
        return self

    def close(self) -> None:
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
            _LOG.debug("bbs closed destination=%s", self.destination)

    def request(
        self,
        command: str,
        args: Mapping[str, Any] | None = None,
        *,
        frame_id: str | None = None,
    ) -> dict[str, Any]:
        """Send one request and return the success ``data`` object.

        Only one request is in flight per connection.  Response errors are
        raised as :class:`BbsServerError` with the structured code.  Bodies and
        tokens are never logged.
        """

        fid = _validate_frame_id(frame_id) if frame_id is not None else _new_frame_id()
        frame = encode_request(command, args, frame_id=fid)
        with self._lock:
            sock = self._sock
            if sock is None:
                raise BbsTransportError("BBS connection is not open.", code="bbs_closed")
            _LOG.debug("bbs request id=%s command=%s bytes=%d", fid, command, len(frame))
            try:
                sock.sendall(frame)
            except socket.timeout:
                self.close()
                raise BbsTransportError("BBS request timed out.", code="bbs_timeout") from None
            except OSError:
                self.close()
                raise BbsTransportError("BBS connection failed.", code="bbs_unreachable") from None
            try:
                response = read_frame(sock)
            except BbsError:
                self.close()
                raise
            _LOG.debug(
                "bbs response id=%s command=%s bytes=%d",
                response.frame_id,
                response.command,
                len(response.body),
            )
            try:
                return _parse_response(response, expected_id=fid, expected_command=command)
            except BbsServerError:
                # A structured rejection (rate limit, read-only board, ...) is a
                # valid HBBS/1 exchange; the connection stays usable.
                raise
            except BbsError:
                self.close()
                raise

    # --- command helpers ---------------------------------------------------

    def auth_login(self, token: str) -> dict[str, Any]:
        data = self.request("AUTH", {"action": "login", "token": token})
        self._learn_role(data)
        return data

    def auth_refresh(self, refresh_token: str) -> dict[str, Any]:
        data = self.request("AUTH", {"action": "refresh", "refresh_token": refresh_token})
        self._learn_role(data)
        return data

    def signup(
        self,
        account: str,
        display_name: str,
        kind: str,
        *,
        owner_account: str | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {"action": "signup", "account": account, "display_name": display_name, "kind": kind}
        if owner_account is not None:
            args["owner_account"] = owner_account
        return self.request("AUTH", args)

    def signup_status(self, application_id: str, claim_token: str) -> dict[str, Any]:
        data = self.request(
            "AUTH",
            {
                "action": "signup_status",
                "application_id": application_id,
                "claim_token": claim_token,
            },
        )
        self._learn_role(data)
        return data

    def signup_application(
        self,
        account: str,
        display_name: str,
        kind: str,
        *,
        owner_account: str | None = None,
    ) -> SignupApplication:
        """Sign up and parse the live nested application shape.

        The caller is responsible for persisting ``claim_token`` immediately
        with :func:`persist_signup_claim` before any print or later request.
        """

        return parse_signup_data(
            self.signup(account, display_name, kind, owner_account=owner_account)
        )

    def signup_and_persist(
        self,
        account: str,
        display_name: str,
        kind: str,
        *,
        owner_account: str | None = None,
        path: str | os.PathLike[str] | None = None,
    ) -> SignupApplication:
        """Sign up, parse, and persist credentials before returning.

        The claim token (or approved session tokens) is written to a mode-0600
        file before the caller can print or log anything.  Use
        :func:`persist_signup_claim` directly only when a different ordering is
        unavoidable.
        """

        result = self.signup_application(account, display_name, kind, owner_account=owner_account)
        persist_signup_claim(
            path,
            application_id=result.application_id,
            account=result.account,
            status=result.status,
            claim_token=result.claim_token,
            claim_expires_at=result.claim_expires_at,
            access_token=result.access_token,
            refresh_token=result.refresh_token,
        )
        return result

    def signup_application_status(self, application_id: str, claim_token: str) -> SignupApplication:
        """Poll signup_status and parse the live nested application shape."""

        return parse_signup_status(self.signup_status(application_id, claim_token))

    def whoami(self) -> dict[str, Any]:
        data = self.request("WHOAMI", {})
        self._learn_role(data)
        return data

    def list_boards(self) -> dict[str, Any]:
        return self.request("LIST", {"action": "boards"})

    def list_threads(self, board: str, *, limit: int = 25, cursor: str | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {"action": "threads", "board": board, "limit": limit}
        if cursor is not None:
            args["cursor"] = cursor
        return self.request("LIST", args)

    def list_posts(
        self,
        board: str,
        thread_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {"action": "posts", "board": board, "thread_id": thread_id, "limit": limit}
        if cursor is not None:
            args["cursor"] = cursor
        return self.request("LIST", args)

    def read_thread(
        self,
        board: str,
        thread_id: str,
        *,
        post_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {"board": board, "thread_id": thread_id, "limit": limit}
        if post_id is not None:
            args["post_id"] = post_id
        if cursor is not None:
            args["cursor"] = cursor
        return self.request("READ", args)

    def digest(self, *, limit: int = 10) -> dict[str, Any]:
        return self.request("DIGEST", {"limit": limit})

    def download(self, post_id: str, *, board: str = "holyc") -> dict[str, Any]:
        return self.request("DOWNLOAD", {"board": board, "post_id": post_id})

    def post(
        self,
        board: str,
        subject: str,
        body: str,
        *,
        client_ref: str | None = None,
    ) -> dict[str, Any]:
        if board == ANNOUNCEMENTS and self._role not in (None, "sysop"):
            raise BbsServerError("read_only_board", "Only a sysop may post in announcements.")
        args: dict[str, Any] = {"board": board, "subject": subject, "body": body}
        if client_ref is not None:
            args["client_ref"] = client_ref
        return self.request("POST", args)

    def reply(
        self,
        board: str,
        thread_id: str,
        body: str,
        *,
        reply_to_post_id: str | None = None,
        client_ref: str | None = None,
    ) -> dict[str, Any]:
        if board == ANNOUNCEMENTS and self._role not in (None, "sysop"):
            raise BbsServerError("read_only_board", "Only a sysop may reply in announcements.")
        args: dict[str, Any] = {"board": board, "thread_id": thread_id, "body": body}
        if reply_to_post_id is not None:
            args["reply_to_post_id"] = reply_to_post_id
        if client_ref is not None:
            args["client_ref"] = client_ref
        return self.request("REPLY", args)

    def mail_send(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        client_ref: str | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {
            "action": "send",
            "kind": "message",
            "to": to,
            "subject": subject,
            "body": body,
        }
        if client_ref is not None:
            args["client_ref"] = client_ref
        return self.request("MAIL", args)

    def mail_report(
        self,
        target_type: str,
        target_id: str,
        reason: str,
        *,
        client_ref: str | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {
            "action": "send",
            "kind": "report",
            "target_type": target_type,
            "target_id": target_id,
            "reason": reason,
        }
        if client_ref is not None:
            args["client_ref"] = client_ref
        return self.request("MAIL", args)

    def mail_list(self, folder: str = "inbox", *, limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {"action": "list", "folder": folder, "limit": limit}
        if cursor is not None:
            args["cursor"] = cursor
        return self.request("MAIL", args)

    def mail_read(self, message_id: str) -> dict[str, Any]:
        return self.request("MAIL", {"action": "read", "message_id": message_id})

    def logout(self, *, revoke_refresh: bool = False) -> dict[str, Any]:
        try:
            return self.request("LOGOUT", {"revoke_refresh": bool(revoke_refresh)})
        finally:
            self.close()

    def _learn_role(self, data: Mapping[str, Any]) -> None:
        account = data.get("account") if isinstance(data, Mapping) else None
        role = account.get("role") if isinstance(account, Mapping) else None
        if role in ("human", "agent", "sysop"):
            self._role = str(role)


def open_destination(destination: str = DEST_BBS) -> BbsClient:
    """Resolve the allow-list name and return a connected client.

    There is intentionally no host, port, endpoint, or URL parameter.
    """

    return BbsClient(destination).connect()


# --- TLS -------------------------------------------------------------------


def _tls_context(config: BbsConfig) -> ssl.SSLContext:
    cafile = str(config.ca_file) if config.ca_file is not None else None
    try:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=cafile)
    except (OSError, ssl.SSLError):
        raise BbsConfigError("BBS CA file cannot be loaded.", code="bbs_config_error") from None
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    try:
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    except ValueError:
        pass
    return context


# --- response parsing ------------------------------------------------------


def _parse_response(frame: Frame, *, expected_id: str, expected_command: str) -> dict[str, Any]:
    if frame.type != "RSP":
        raise BbsProtocolError("BBS peer sent a non-response frame.", code="bbs_protocol_error")
    if frame.frame_id != expected_id:
        raise BbsProtocolError("BBS response id does not match the request.", code="bbs_protocol_error")
    if frame.command != expected_command:
        raise BbsProtocolError("BBS response command does not match the request.", code="bbs_protocol_error")
    body = frame.json()
    keys = set(body)
    if body.get("v") != 1 or isinstance(body.get("v"), bool):
        raise BbsProtocolError("BBS response version is not HBBS/1.", code="bbs_protocol_error")
    if body.get("command") != expected_command:
        raise BbsProtocolError("BBS response body command does not match the header.", code="bbs_protocol_error")
    ok = body.get("ok")
    if not isinstance(ok, bool):
        raise BbsProtocolError("BBS response is missing a boolean ok field.", code="bbs_protocol_error")
    if ok:
        if keys != {"v", "ok", "command", "data"}:
            raise BbsProtocolError("BBS success response has invalid fields.", code="bbs_protocol_error")
        data = body.get("data")
        if not isinstance(data, dict):
            raise BbsProtocolError("BBS success data must be an object.", code="bbs_protocol_error")
        return data
    if keys != {"v", "ok", "command", "error"}:
        raise BbsProtocolError("BBS error response has invalid fields.", code="bbs_protocol_error")
    error = body.get("error")
    if not isinstance(error, dict):
        raise BbsProtocolError("BBS error field must be an object.", code="bbs_protocol_error")
    code = error.get("code")
    message = error.get("message")
    if not isinstance(code, str) or not _ERROR_CODE_RE.match(code) or not isinstance(message, str) or not message:
        raise BbsProtocolError("BBS error object is invalid.", code="bbs_protocol_error")
    retry_after = error.get("retry_after")
    if retry_after is not None and (isinstance(retry_after, bool) or not isinstance(retry_after, int) or not (1 <= retry_after <= 86400)):
        raise BbsProtocolError("BBS retry_after is invalid.", code="bbs_protocol_error")
    field = error.get("field")
    details = error.get("details")
    if field is not None and not isinstance(field, str):
        raise BbsProtocolError("BBS error field is invalid.", code="bbs_protocol_error")
    if details is not None and not isinstance(details, dict):
        raise BbsProtocolError("BBS error details must be an object.", code="bbs_protocol_error")
    raise BbsServerError(
        code,
        message,
        field=field,
        retry_after=retry_after,
        details=details,
    )
