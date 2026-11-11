"""Plugin-side chat bridge for the temple-of-hermes chat relay.

The host relay owns the transcript and decides when to speak. Its
``ChatResponder`` can call this module's ``reply(text)`` to hand one finished
reply to a Hermes agent. Nothing here invents an answer: when the bridge is
disabled or no agent is reachable, ``reply`` raises a typed error and the
relay can keep its offline ``HermesResponder`` fallback.

Configuration comes only from the process environment (or an explicit
``ChatBridgeConfig``). No host, URL, port, or path is baked into this module.

Environment
-----------
``TEMPLEOS_CHAT_BRIDGE``
    ``1``/``true``/``yes``/``on`` enables the bridge. Anything else disables it.
``TEMPLEOS_CHAT_BRIDGE_ENDPOINT``
    ``http`` or ``https`` URL of the agent reply endpoint. Required for the
    built-in HTTP transport; its value is never echoed in errors.
``TEMPLEOS_CHAT_BRIDGE_TOKEN``
    Optional bearer token sent in the ``Authorization`` header. Read only
    through ``agent.secret_scope.get_secret`` (declared in ``requires_env``).
    Never read from ``os.environ``, never logged, and excluded from ``repr``.
``TEMPLEOS_CHAT_BRIDGE_TIMEOUT_S``
    Optional positive request timeout; defaults to 20 seconds.

Wire contract (built-in transport)
----------------------------------
Request: ``POST <endpoint>`` with ``Content-Type: application/json`` and body
``{"text": "<reply text>"}``; optionally ``Authorization: Bearer <token>``.
Response: JSON object ``{"reply": "..."}`` or ``{"text": "..."}``, a JSON
string, or a plain-text body. An empty body is an error.

The bridge is not a Hermes tool. ``templeos.tools.TOOL_NAMES`` stays at four
entries; the relay imports this module directly.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from templeos.public_http import UnsafeURL, request as pinned_request, split_url

ENV_ENABLED = "TEMPLEOS_CHAT_BRIDGE"
ENV_ENDPOINT = "TEMPLEOS_CHAT_BRIDGE_ENDPOINT"
ENV_TOKEN = "TEMPLEOS_CHAT_BRIDGE_TOKEN"
ENV_TIMEOUT = "TEMPLEOS_CHAT_BRIDGE_TIMEOUT_S"

DEFAULT_TIMEOUT_S = 20.0
MAX_TIMEOUT_S = 300.0
MAX_REPLY_BYTES = 2 * 1024 * 1024

_TRUTHY = frozenset({"1", "true", "yes", "on"})

Transport = Callable[[str], str]


class ChatBridgeError(RuntimeError):
    """Base error. Messages are safe to show: they never include secrets."""


class ChatBridgeDisabled(ChatBridgeError):
    """The bridge is switched off by configuration."""


class ChatBridgeUnavailable(ChatBridgeError):
    """The bridge is enabled but no agent (or no usable reply) is available."""


def _enabled(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in _TRUTHY


def _timeout(value: str | None) -> float:
    if not value:
        return DEFAULT_TIMEOUT_S
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ChatBridgeError("chat bridge timeout must be a number of seconds") from exc
    if parsed <= 0 or parsed > MAX_TIMEOUT_S:
        raise ChatBridgeError(
            f"chat bridge timeout must be between 0 and {int(MAX_TIMEOUT_S)} seconds"
        )
    return parsed


def _endpoint(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        split_url(text)
    except UnsafeURL as exc:
        # Never echo the configured value; it may contain credentials.
        raise ChatBridgeError("chat bridge endpoint must be an http or https URL") from exc
    return text


def _secret_token() -> str | None:
    """Return the bridge token from Hermes secret scope only. Fail closed."""
    try:
        from agent.secret_scope import get_secret
    except Exception:
        return None
    try:
        value = get_secret(ENV_TOKEN)
    except Exception:
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class ChatBridgeConfig:
    """Bridge settings. ``token`` is intentionally absent from ``repr``."""

    enabled: bool = False
    endpoint: str | None = None
    token: str | None = field(default=None, repr=False)
    timeout_s: float = DEFAULT_TIMEOUT_S

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ChatBridgeConfig":
        env = os.environ if environ is None else environ
        return cls(
            enabled=_enabled(env.get(ENV_ENABLED)),
            endpoint=_endpoint(env.get(ENV_ENDPOINT)),
            token=_secret_token(),
            timeout_s=_timeout(env.get(ENV_TIMEOUT)),
        )

    def has_agent(self) -> bool:
        return bool(self.endpoint)


def _decode_reply(raw: bytes) -> str:
    try:
        body = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ChatBridgeUnavailable("agent reply was not valid UTF-8") from exc
    if not body:
        raise ChatBridgeUnavailable("agent returned an empty reply")
    reply: Any = body
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        for key in ("reply", "text", "message"):
            value = parsed.get(key)
            if isinstance(value, str):
                reply = value
                break
        else:
            raise ChatBridgeUnavailable("agent reply JSON has no reply/text field")
    elif isinstance(parsed, str):
        reply = parsed
    if not isinstance(reply, str) or not reply.strip():
        raise ChatBridgeUnavailable("agent returned no reply text")
    return reply


def _http_transport(config: ChatBridgeConfig) -> Transport:
    def send(text: str) -> str:
        if not config.endpoint:
            raise ChatBridgeUnavailable(
                "chat bridge has no agent endpoint configured; "
                f"set {ENV_ENDPOINT} or use the relay's offline responder"
            )
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain",
        }
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
        try:
            status, raw = pinned_request(
                config.endpoint,
                method="POST",
                body=json.dumps({"text": text}).encode("utf-8"),
                headers=headers,
                timeout=config.timeout_s,
                max_redirects=0,
                allow_loopback=True,
                allow_private=True,
                https_only=False,
                max_bytes=MAX_REPLY_BYTES,
            )
        except (UnsafeURL, OSError, ValueError, TimeoutError) as exc:
            # Deliberately no endpoint/token in the message.
            raise ChatBridgeUnavailable(
                f"chat bridge agent is unreachable ({type(exc).__name__})"
            ) from None
        if status < 200 or status >= 300:
            raise ChatBridgeUnavailable("chat bridge agent is unreachable (HTTPError)")
        if len(raw) > MAX_REPLY_BYTES:
            raise ChatBridgeUnavailable("agent reply exceeds the bridge size limit")
        return _decode_reply(raw)

    return send


class ChatBridge:
    """Forwards one finished relay reply to an agent.

    ``transport`` is a callable ``text -> reply`` used by tests and by hosts
    that already own a loopback channel. When omitted, an enabled config with
    an endpoint uses the built-in HTTP transport.
    """

    def __init__(self, config: ChatBridgeConfig, transport: Transport | None = None) -> None:
        self.config = config
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    def available(self) -> bool:
        return self.enabled and (self._transport is not None or self.config.has_agent())

    def reply(self, text: str) -> str:
        """Return the agent's reply for ``text`` or raise a typed bridge error."""
        if not isinstance(text, str) or not text.strip():
            raise ChatBridgeError("chat bridge reply text must be a non-empty string")
        if not self.enabled:
            raise ChatBridgeDisabled(
                f"chat bridge is disabled; set {ENV_ENABLED}=1 to enable it"
            )
        transport = self._transport
        if transport is None:
            if not self.config.has_agent():
                raise ChatBridgeUnavailable(
                    "chat bridge has no agent endpoint configured; "
                    "use the relay's offline responder"
                )
            transport = _http_transport(self.config)
        try:
            answer = transport(text)
        except ChatBridgeError:
            raise
        except Exception as exc:
            raise ChatBridgeUnavailable(
                f"chat bridge agent failed ({type(exc).__name__})"
            ) from None
        if not isinstance(answer, str) or not answer.strip():
            raise ChatBridgeUnavailable("agent returned no reply text")
        return answer

    def try_reply(self, text: str) -> str | None:
        """``reply`` for relays that prefer a ``None`` fallback over an exception."""
        try:
            return self.reply(text)
        except ChatBridgeError:
            return None


def build_bridge(
    config: ChatBridgeConfig | None = None,
    transport: Transport | None = None,
) -> ChatBridge:
    return ChatBridge(config or ChatBridgeConfig.from_env(), transport)


_DEFAULT: ChatBridge | None = None
_DEFAULT_LOCK = threading.Lock()


def get_bridge() -> ChatBridge:
    """Lazily build the process-wide bridge from the current environment."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            _DEFAULT = build_bridge()
        return _DEFAULT


def reset_bridge() -> None:
    """Forget the cached default (used after configuration changes and by tests)."""
    global _DEFAULT
    with _DEFAULT_LOCK:
        _DEFAULT = None


def reply(text: str) -> str:
    """Host-relay entrypoint: forward ``text`` and return the agent's reply."""
    return get_bridge().reply(text)


def try_reply(text: str) -> str | None:
    """Host-relay entrypoint that returns ``None`` when the bridge cannot reply."""
    return get_bridge().try_reply(text)
