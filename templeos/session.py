"""Host-side community operations: session summary, BBS digest, codeshare.

Everything here is a host helper behind the existing four tools. Fetched HolyC
is staged under the plugin data dir, pushed only into the guest Src/ folder,
and can run only through the guest input path. Nothing is executed on the host.
"""

from __future__ import annotations

import getpass
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from templeos import bbs, nudge
from templeos.paths import home

DEFAULT_JOURNAL_LINES = 5
MAX_JOURNAL_LINES = 10
MAX_LINE_CHARS = 200
MAX_CODE_BYTES = 32 * 1024
GUEST_RUN_TIMEOUT_S = 15.0
DEFAULT_HANDLE = "hermes"
ENV_HANDLE = "TEMPLEOS_HANDLE"
MAX_DIGEST_ITEMS = 10
MAX_SUBJECT_CHARS = 60

_HANDLE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_ACCOUNT_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
_POST_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_COUNT_KEYS = ("replies", "mentions", "unread", "unread_replies", "mail", "unread_mail", "threads", "posts")
_DIGEST_LATEST_KEYS = ("mail", "mentions", "replies", "followed_boards")
_DIGEST_ID_KEYS = ("post_id", "thread_id", "message_id", "board_id", "mention_id", "reply_id", "id")
_DIGEST_TITLE_KEYS = ("subject", "title", "name", "display_name")
_DIGEST_UNSUPPORTED_CODES = frozenset(
    {"unknown_command", "unsupported_command", "unsupported_action", "command_not_found", "invalid_action", "not_implemented"}
)
_SOURCE_KEYS = ("source", "code", "holyc", "body", "text", "content")


class OpsError(Exception):
    def __init__(self, message: str, code: str, fix: str | None = None, **fields: Any) -> None:
        super().__init__(message)
        self.code = code
        self.fix = fix
        self.fields = fields
        self.envelope = {"error": message, "code": code, "fix": fix, **fields}


def _handle(handle: str | None = None) -> str:
    value = (handle or os.environ.get(ENV_HANDLE) or DEFAULT_HANDLE).strip()
    if not _HANDLE_RE.match(value) or value in (".", ".."):
        raise OpsError(
            "handle must be 1-32 letters, digits, dots, dashes, or underscores.",
            "invalid_args",
            "Pass a simple guest home handle, e.g. handle=hermes.",
        )
    return value


def guest_home(handle: str | None = None) -> str:
    return f"C:/Home/{_handle(handle)}"


def _clean_line(value: Any, limit: int = MAX_LINE_CHARS) -> str:
    text = str(value or "").replace("\x00", " ")
    text = " ".join(text.split())
    return text[:limit]


def _read_guest_text(guest_path: str, pull: Callable[..., Mapping[str, Any]] | None = None) -> str:
    root = home()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix=".session-") as tmp:
        dest = Path(tmp) / "file.txt"
        fn = pull
        if fn is None:
            from templeos.files import pull as fn
        result = fn(guest_path, dest)
        if not isinstance(result, Mapping) or result.get("ok") is False:
            raise OpsError(
                f"Could not read {guest_path} from the guest.",
                "session_unavailable",
                "Start the guest, load the Xfer helper, and create the Home journal/projects files.",
            )
        try:
            return dest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise OpsError(
                f"Could not read {guest_path} after transfer.",
                "session_unavailable",
                "Retry once the guest serial file helper is responsive.",
            ) from None


def _journal_lines(text: str, limit: int) -> list[str]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [_clean_line(line) for line in raw if _clean_line(line)]
    return lines[-limit:]


def _projects_summary(text: str) -> tuple[str | None, str | None]:
    current = None
    next_step = None
    fallback: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _clean_line(raw)
        if not line:
            continue
        key, sep, value = line.partition(":")
        if not sep:
            key, sep, value = line.partition("=")
        if sep:
            normalized = re.sub(r"[^a-z]+", "", key.lower())
            if normalized in ("current", "project", "currentproject"):
                current = _clean_line(value)
                continue
            if normalized in ("next", "nextstep", "todo"):
                next_step = _clean_line(value)
                continue
        fallback.append(line)
    if current is None and fallback:
        current = fallback[0]
    if next_step is None and len(fallback) > 1:
        next_step = fallback[1]
    return current, next_step


def session_start(
    *,
    limit: int = DEFAULT_JOURNAL_LINES,
    handle: str | None = None,
    pull: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        lines_wanted = int(limit)
    except (TypeError, ValueError):
        raise OpsError("limit must be an integer.", "invalid_args", "Use limit 1-10.")
    lines_wanted = max(1, min(MAX_JOURNAL_LINES, lines_wanted))
    home_guest = guest_home(handle)
    journal_path = f"{home_guest}/JOURNAL.TXT"
    projects_path = f"{home_guest}/PROJECTS.TXT"
    journal_text = _read_guest_text(journal_path, pull)
    projects_text = _read_guest_text(projects_path, pull)
    journal = _journal_lines(journal_text, lines_wanted)
    project, next_step = _projects_summary(projects_text)
    if not journal and project is None and next_step is None:
        raise OpsError(
            "The session files are present but empty.",
            "session_unavailable",
            "Write a journal line and a project/next step in the guest Home folder.",
        )
    if project or next_step:
        nudge.record_pending(project=project, next_step=next_step)
    return {
        "ok": True,
        "handle": _handle(handle),
        "journal": journal,
        "journal_count": len(journal),
        "project": project,
        "next_step": next_step,
    }


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_id(value: Any) -> str | None:
    text = str(value or "")
    return text if _POST_RE.match(text) else None


def _safe_subject(value: Any) -> str:
    text = _clean_line(value, MAX_SUBJECT_CHARS)
    return text


def _digest_latest_items(value: Any) -> list[Any]:
    """Return the latest/items/recent list for one digest section."""

    if isinstance(value, Mapping):
        for key in ("latest", "items", "recent"):
            items = value.get(key)
            if isinstance(items, list):
                return items
        return []
    if isinstance(value, list):
        return value
    return []


def _normalize_digest(data: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce an HBBS/1 digest to counts, safe ids, short subjects, and pending.

    Handles the section 17.2 nested shape ``{"digest": {...}}`` (mail.unread,
    mentions.pending, replies.count, latest arrays) and the older flat
    counts/ids/subjects fixture.  Only whitelisted scalar fields survive;
    tokens, bodies, and unknown keys are dropped.
    """

    source: Mapping[str, Any] = data
    nested = data.get("digest")
    if isinstance(nested, Mapping):
        source = nested
    counts: dict[str, int] = {}

    counts_block = data.get("counts")
    if isinstance(counts_block, Mapping):
        for key in _COUNT_KEYS:
            if key in counts_block:
                counts[key] = _count(counts_block.get(key))

    for section, field, count_key in (
        ("mail", "unread", "mail"),
        ("mentions", "pending", "mentions"),
        ("replies", "count", "replies"),
    ):
        block = source.get(section)
        if isinstance(block, Mapping) and field in block:
            counts[count_key] = _count(block.get(field))

    for key in _COUNT_KEYS:
        if key in source and not isinstance(source.get(key), Mapping) and key not in counts:
            counts[key] = _count(source.get(key))

    ids: list[str] = []
    seen_ids: set[str] = set()

    def add_id(value: Any) -> None:
        safe = _safe_id(value)
        if safe and safe not in seen_ids:
            seen_ids.add(safe)
            ids.append(safe)

    for container in (data, source):
        for key in ("ids", "post_ids", "thread_ids"):
            values = container.get(key)
            if isinstance(values, list):
                for value in values:
                    add_id(value)

    subjects: list[str] = []

    def add_subject(value: Any) -> None:
        text = _safe_subject(value)
        if text and text not in subjects:
            subjects.append(text)

    items = data.get("subjects")
    if items is None:
        items = data.get("items") if isinstance(data.get("items"), list) else data.get("recent")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, Mapping):
                title = next((item.get(key) for key in _DIGEST_TITLE_KEYS if item.get(key)), None)
            else:
                title = item
            add_subject(title)

    for key in _DIGEST_LATEST_KEYS:
        for item in _digest_latest_items(source.get(key)):
            if isinstance(item, Mapping):
                for id_key in _DIGEST_ID_KEYS:
                    if id_key in item:
                        add_id(item.get(id_key))
                title = next((item.get(title_key) for title_key in _DIGEST_TITLE_KEYS if item.get(title_key)), None)
                add_subject(title)
            elif key == "followed_boards":
                add_id(item)
                add_subject(item)
            else:
                add_subject(item)

    replies = counts.get("replies", 0) + counts.get("unread_replies", 0)
    mail = counts.get("mail", 0) + counts.get("unread_mail", 0)
    mentions = counts.get("mentions", 0)
    unread = counts.get("unread", 0)
    pending = max(replies + mail + mentions, unread)
    return {
        "counts": counts,
        "ids": ids[:MAX_DIGEST_ITEMS],
        "subjects": subjects[:MAX_DIGEST_ITEMS],
        "pending": pending,
        "truncated": len(ids) > MAX_DIGEST_ITEMS or len(subjects) > MAX_DIGEST_ITEMS,
    }


def _bbs_failure(exc: BaseException) -> OpsError:
    code = getattr(exc, "code", None) or "bbs_unavailable"
    if code == "bbs_disabled":
        return OpsError(
            "The BBS is turned off (bbs.json enabled:false or TOH_BBS_ENABLED=0).",
            "bbs_disabled",
            "Turn it on with bbs.json enabled:true (or unset TOH_BBS_ENABLED), then run templeos_vm op=bbs_join.",
        )
    if code == "bbs_config_error":
        return OpsError(
            "The BBS endpoint is invalid.",
            "bbs_not_configured",
            "Fix the host bbs.json or TOH_BBS_ENDPOINT value; the built-in community BBS is already the default.",
        )
    if code in ("bbs_tls_error", "bbs_unreachable", "bbs_closed", "bbs_timeout"):
        return OpsError(
            "The community BBS is unreachable.",
            str(code),
            "Retry once; do not probe DNS, ports, vhosts, or other hosts.",
        )
    return OpsError(
        "The BBS request failed.",
        str(code),
        "Retry once; if it persists, run templeos_vm op=bbs_join or check the plugin log.",
    )


def _iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_display(value: Any, fallback: str) -> str:
    text = " ".join(str(value or "").split())
    text = "".join(ch for ch in text if 0x20 <= ord(ch) <= 0x7E)[:32].strip()
    return text or (fallback[:32] or "Temple human")


def _sanitize_account(raw: Any) -> str:
    text = re.sub(r"[^a-z0-9_.-]+", "", str(raw or "").lower())
    text = text.lstrip("._-")
    if len(text) < 3:
        text = "toh-" + (text or "hermes")
    elif not text.startswith("toh-"):
        text = "toh-" + text
    text = text[:32].rstrip("._-")
    if not _ACCOUNT_RE.match(text):
        text = "toh-hermes"
    return text


def _variant_account(base: str, index: int) -> str:
    if index <= 0:
        return base[:32]
    suffix = str(index + 1)
    return (base[: 32 - len(suffix)] + suffix).rstrip("._-")


def _new_client(factory: Callable[..., Any] | None) -> Any:
    client = _open_client(factory)
    if hasattr(client, "connect"):
        client.connect()
    return client


def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _rate_limit_wait(exc: BaseException) -> bool:
    """Sleep once for a server ``rate_limited`` retry_after.  Cap at 60 s."""

    if not isinstance(exc, bbs.BbsServerError) or exc.code != "rate_limited":
        return False
    raw = getattr(exc, "retry_after", None)
    try:
        wait = int(raw) if raw is not None else 24
    except (TypeError, ValueError):
        wait = 24
    wait = min(max(wait, 1), 60)
    time.sleep(wait)
    return True


def _call_with_rate_limit(fn: Callable[[], Any]) -> Any:
    """Run *fn* and retry once after ``rate_limited`` / retry_after."""

    try:
        return fn()
    except bbs.BbsServerError as exc:
        if _rate_limit_wait(exc):
            return fn()
        raise


def _refresh_creds(client: Any, creds: Mapping[str, str], path: Path) -> str | None:
    token = creds.get("REFRESH_TOKEN")
    if not token:
        return None
    data = _call_with_rate_limit(lambda: client.auth_refresh(token))
    access, refresh, account = bbs.extract_tokens(data)
    resolved = account or creds.get("ACCOUNT")
    if not resolved:
        raise bbs.BbsProtocolError("BBS refresh response has no account.", code="bbs_protocol_error")
    bbs.persist_credentials(
        path,
        account=resolved,
        access_token=access,
        refresh_token=refresh,
        status="approved",
    )
    return resolved


def _signup_application(
    *,
    base: str,
    display: str,
    kind: str,
    path: Path,
    factory: Callable[..., Any] | None,
    owner_account: str | None = None,
) -> Any:
    last = "account_exists"
    for index in range(5):
        account = _variant_account(base, index)
        dest = bbs.new_credentials_path(kind, account)
        client = None
        try:
            client = _new_client(factory)
            app = _call_with_rate_limit(
                lambda dest=dest, account=account: client.signup_and_persist(
                    account,
                    display,
                    kind,
                    owner_account=owner_account,
                    path=dest,
                )
            )
            return app
        except bbs.BbsServerError as exc:
            last = exc.code
            if exc.code == "rate_limited":
                # _call_with_rate_limit already retried once; surface the error.
                raise _bbs_failure(exc) from None
            if exc.code in ("account_exists", "account_pending"):
                continue
            if exc.code in ("owner_required", "owner_not_eligible"):
                raise OpsError(
                    "The agent owner is missing or not an active human.",
                    exc.code,
                    "Run templeos_vm op=bbs_join again; the human account must be approved first.",
                ) from None
            raise _bbs_failure(exc) from None
        finally:
            _close_client(client)
    raise OpsError(
        f"Could not find a free {kind} account name.",
        last,
        "Pass a different account argument to templeos_vm op=bbs_join.",
    )


def bbs_status(*, config_factory: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Secret-free BBS state for /status and the pane chip.  Never dials."""

    body: dict[str, Any] = {
        "enabled": False,
        "configured": False,
        "joined": False,
        "account": None,
        "last_ok": None,
        "error": None,
    }
    try:
        config = (config_factory or bbs.load_config)()
    except bbs.BbsError as exc:
        body["enabled"] = True
        body["error"] = getattr(exc, "code", None) or "bbs_config_error"
        return body
    except Exception:
        body["enabled"] = True
        body["error"] = "bbs_config_error"
        return body
    enabled = bool(getattr(config, "enabled", False))
    body["enabled"] = enabled
    body["configured"] = bool(enabled and getattr(config, "host", None) and getattr(config, "port", 0))
    if not enabled:
        body["error"] = "bbs_disabled"
        return body
    path, creds = bbs.discover_credentials("agent")
    account = creds.get("ACCOUNT")
    joined = bool(account and (creds.get("ACCESS_TOKEN") or creds.get("REFRESH_TOKEN")))
    body["joined"] = joined
    body["account"] = account if joined else None
    if joined:
        try:
            body["last_ok"] = _iso_utc(path.stat().st_mtime)
        except OSError:
            body["last_ok"] = True
    return body


def bbs_join(
    *,
    handle: str | None = None,
    account: str | None = None,
    display_name: str | None = None,
    client_factory: Callable[..., Any] | None = None,
    config_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Idempotent human-then-agent community BBS join.

    Tokens are persisted before returning and never appear in the envelope.
    The human is created/refreshed first, then the agent under that human.
    """

    try:
        config = (config_factory or bbs.load_config)()
    except bbs.BbsError as exc:
        raise _bbs_failure(exc) from None
    except Exception:
        raise OpsError(
            "The BBS endpoint is invalid.",
            "bbs_not_configured",
            "Fix the host bbs.json or TOH_BBS_ENDPOINT value.",
        ) from None
    if not getattr(config, "enabled", False):
        raise _bbs_failure(bbs.BbsDisabledError("The BBS is turned off.", code="bbs_disabled"))

    human_path, human_creds = bbs.discover_credentials("human")
    agent_path, agent_creds = bbs.discover_credentials("agent")

    # 1. A stored agent refresh token is the cheapest idempotent path.
    if agent_creds.get("REFRESH_TOKEN"):
        client = None
        try:
            client = _new_client(client_factory)
            agent_account = _refresh_creds(client, agent_creds, agent_path)
            return {
                "ok": True,
                "joined": True,
                "human_account": human_creds.get("ACCOUNT") or None,
                "agent_account": agent_account,
                "status": "joined",
            }
        except bbs.BbsServerError:
            pass  # token error: fall through to a fresh sign-up
        except bbs.BbsError as exc:
            raise _bbs_failure(exc) from None
        finally:
            _close_client(client)

    # 2. Reuse or refresh a stored human; otherwise sign one up.
    human_account = None
    if human_creds.get("REFRESH_TOKEN"):
        client = None
        try:
            client = _new_client(client_factory)
            human_account = _refresh_creds(client, human_creds, human_path)
        except bbs.BbsServerError:
            human_account = None
        except bbs.BbsError as exc:
            raise _bbs_failure(exc) from None
        finally:
            _close_client(client)
    elif human_creds.get("ACCOUNT") and human_creds.get("ACCESS_TOKEN"):
        human_account = human_creds.get("ACCOUNT")

    if not human_account:
        base = _sanitize_account(account or handle or getpass.getuser())
        display = _safe_display(display_name, base)
        app = _signup_application(
            base=base,
            display=display,
            kind="human",
            path=human_path,
            factory=client_factory,
        )
        human_account = app.account
        if not app.approved:
            return {
                "ok": True,
                "joined": False,
                "human_account": human_account,
                "agent_account": None,
                "status": app.status,
            }
        human_display = app.display_name or display
    else:
        human_display = _safe_display(display_name, human_account)

    # 3. A NEW connection signs the agent under the active human.
    agent_base = (_variant_account(human_account, 0)[:26].rstrip("._-") + "-agent")[:32]
    agent_app = _signup_application(
        base=agent_base,
        display=_safe_display(None, human_display)[:24] + " agent",
        kind="agent",
        path=agent_path,
        factory=client_factory,
        owner_account=human_account,
    )
    if not agent_app.approved:
        return {
            "ok": True,
            "joined": False,
            "human_account": human_account,
            "agent_account": agent_app.account,
            "status": agent_app.status,
        }
    return {
        "ok": True,
        "joined": True,
        "human_account": human_account,
        "agent_account": agent_app.account,
        "status": "joined",
    }


def _connect_authenticated(factory: Callable[..., Any] | None) -> Any:
    if factory is not None:
        return _new_client(factory)
    path, creds = bbs.discover_credentials("agent")
    refresh = creds.get("REFRESH_TOKEN")
    access = creds.get("ACCESS_TOKEN")
    if not refresh and not access:
        raise OpsError(
            "The community BBS is not joined on this host.",
            "bbs_not_joined",
            "Run templeos_vm op=bbs_join (human first, then the agent under that human).",
        )
    client = _new_client(factory)
    try:
        if refresh:
            _refresh_creds(client, creds, path)
        else:
            _call_with_rate_limit(lambda: client.auth_login(access))
    except bbs.BbsError as exc:
        _close_client(client)
        raise _bbs_failure(exc) from None
    return client


def _open_client(factory: Callable[..., Any] | None) -> Any:
    if factory is not None:
        return factory()
    return bbs.open_destination()


def bbs_digest(
    *,
    limit: int = 10,
    client_factory: Callable[..., Any] | None = None,
    config_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if client_factory is None:
        try:
            config = (config_factory or bbs.load_config)()
        except bbs.BbsError as exc:
            raise _bbs_failure(exc) from None
        except Exception:
            raise OpsError(
                "The BBS endpoint is invalid.",
                "bbs_not_configured",
                "Fix the host bbs.json or TOH_BBS_ENDPOINT value.",
            ) from None
        if not getattr(config, "enabled", False):
            raise _bbs_failure(bbs.BbsDisabledError("The BBS is turned off.", code="bbs_disabled"))
    client = None
    data: Mapping[str, Any] | None = None
    unsupported = False
    try:
        client = _connect_authenticated(client_factory)
        data = client.digest(limit=max(1, min(20, int(limit))))
    except OpsError:
        raise
    except bbs.BbsServerError as exc:
        rejected_digest_action = exc.code == "invalid_args" and exc.field in (None, "args.action")
        if exc.code in _DIGEST_UNSUPPORTED_CODES or rejected_digest_action:
            # Optional section-17.2 extension: an older server rejects the
            # additive LIST action.  Return an empty compact digest instead of
            # crashing; never include server payloads or tokens.
            unsupported = True
        else:
            raise _bbs_failure(exc) from None
    except bbs.BbsError as exc:
        raise _bbs_failure(exc) from None
    except Exception:
        raise OpsError(
            "The BBS digest request failed.",
            "bbs_unavailable",
            "Check the configured bbs endpoint and retry.",
        ) from None
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    if unsupported:
        return {
            "ok": True,
            "unsupported": True,
            "code": "bbs_digest_unsupported",
            "reason": "bbs_digest_unsupported",
            "counts": {},
            "ids": [],
            "subjects": [],
            "pending": 0,
            "truncated": False,
        }
    if not isinstance(data, Mapping):
        raise OpsError("The BBS digest reply was malformed.", "bbs_protocol_error", "Check the server version.")
    body = _normalize_digest(data)
    nudge.record_pending(bbs_replies=body["pending"])
    return {"ok": True, **body}


def _extract_source(data: Mapping[str, Any]) -> str | None:
    for key in _SOURCE_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in ("post", "source", "download", "item"):
        nested = data.get(key)
        if isinstance(nested, Mapping):
            found = _extract_source(nested)
            if found:
                return found
    return None


def _source_name(data: Mapping[str, Any], post_id: str) -> str:
    name = data.get("filename") or data.get("name") or data.get("path")
    base = Path(str(name)).name if name else f"post-{post_id}"
    base = _FILENAME_RE.sub("-", base).strip("-.") or f"post-{post_id}"
    if len(base) > 48:
        base = base[:48]
    if base.lower().endswith(".hc"):
        base = base[:-3] + ".HC"
    else:
        base += ".HC"
    return base


def _run_in_guest(source: str) -> dict[str, Any]:
    from templeos.input import holyc
    from templeos.screen import wait_idle

    result = holyc(source)
    if not isinstance(result, Mapping) or result.get("ok") is False:
        return dict(result) if isinstance(result, Mapping) else {"ok": False, "code": "vm_not_running"}
    idle = wait_idle(timeout_s=GUEST_RUN_TIMEOUT_S)
    return {"ok": True, "guest_run": dict(idle) if isinstance(idle, Mapping) else None}


def codeshare_fetch(
    post_id: str,
    *,
    run: bool = False,
    handle: str | None = None,
    client_factory: Callable[..., Any] | None = None,
    push: Callable[..., Mapping[str, Any]] | None = None,
    run_source: Callable[[str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    post = str(post_id or "").strip()
    if not _POST_RE.match(post):
        raise OpsError(
            "post_id must be a simple board id.",
            "invalid_args",
            "Use the id from a bbs_digest result.",
        )
    client = None
    try:
        client = _connect_authenticated(client_factory)
        data = client.download(post, board="holyc")
    except OpsError:
        raise
    except bbs.BbsError as exc:
        raise _bbs_failure(exc) from None
    except Exception:
        raise OpsError(
            "The codeshare download failed.",
            "bbs_unavailable",
            "Check the configured bbs endpoint and retry.",
        ) from None
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    if not isinstance(data, Mapping):
        raise OpsError("The codeshare reply was malformed.", "bbs_protocol_error", "Check the server version.")
    source = _extract_source(data)
    if source is None:
        raise OpsError(
            "The codeshare reply did not include HolyC source.",
            "invalid_source",
            "Fetch a post that contains source text.",
        )
    raw = source.encode("utf-8")
    if len(raw) > MAX_CODE_BYTES:
        raise OpsError(
            f"Fetched source exceeds {MAX_CODE_BYTES} bytes.",
            "source_too_large",
            "Choose a smaller post; fetched HolyC is capped at 32 KiB.",
        )
    name = _source_name(data, post)
    guest_path = f"{guest_home(handle)}/Src/{name}"
    root = home()
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=root, prefix=".codeshare-")) / name
    try:
        stage.write_bytes(raw)
        try:
            stage.chmod(0o600)
        except OSError:
            pass
        pusher = push
        if pusher is None:
            from templeos.files import push as pusher
        pushed = pusher(stage, guest_path)
        if not isinstance(pushed, Mapping) or pushed.get("ok") is False:
            raise OpsError(
                "Could not write the fetched source into the guest Src folder.",
                str((pushed or {}).get("code") or "codeshare_push_failed") if isinstance(pushed, Mapping) else "codeshare_push_failed",
                "Start the guest and load the Xfer helper, then retry the fetch.",
            )
    finally:
        try:
            stage.unlink()
        except OSError:
            pass
        try:
            stage.parent.rmdir()
        except OSError:
            pass
    result: dict[str, Any] = {
        "ok": True,
        "post_id": post,
        "guest_path": guest_path,
        "bytes": len(raw),
        "ran": False,
    }
    if run:
        runner = run_source or _run_in_guest
        ran = runner(source)
        if not isinstance(ran, Mapping) or ran.get("ok") is False:
            raise OpsError(
                "The source was saved but the in-guest run failed.",
                str((ran or {}).get("code") or "guest_run_failed") if isinstance(ran, Mapping) else "guest_run_failed",
                "Check that the guest is running at a HolyC prompt, then run it from the guest.",
                guest_path=guest_path,
            )
        result["ran"] = True
        result["guest_run"] = dict(ran)
    return result
