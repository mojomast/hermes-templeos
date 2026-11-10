# PINT chat bridge contract

Status: implemented on the integration working tree, uncommitted.
Owner: plugin side (`templeos/chat_bridge.py`). Host wiring belongs to INT
(`hermes_chat_relay.py`).

## Purpose

The temple-of-hermes host relay owns the chat transcript and its offline
`HermesResponder`. When a Hermes agent is available, `ChatResponder` should be
able to hand one already-finished reply to the agent and get one reply back.
This module is that hand-off. It never composes, guesses, or invents text: if
it cannot reach an agent it raises a typed error (or returns `None` from
`try_reply`), and the relay keeps its offline answer.

The bridge is a module, not a tool. `templeos.tools.TOOL_NAMES` remains the
four `templeos_*` tools, and the o200k schema count stays 892 (delta 0).

## Configuration

All configuration comes from the process environment, or from an explicit
`ChatBridgeConfig` passed by an embedding host. There is no hardcoded host,
URL, port, or filesystem path anywhere in the module.

| Variable | Meaning | Default |
| --- | --- | --- |
| `TEMPLEOS_CHAT_BRIDGE` | `1`/`true`/`yes`/`on` enables the bridge; anything else leaves it disabled | disabled |
| `TEMPLEOS_CHAT_BRIDGE_ENDPOINT` | `http`/`https` URL of the agent reply endpoint | unset |
| `TEMPLEOS_CHAT_BRIDGE_TOKEN` | optional bearer token; never logged and excluded from `repr` | unset |
| `TEMPLEOS_CHAT_BRIDGE_TIMEOUT_S` | request timeout in seconds, `0 < n <= 300` | `20` |

Invalid values fail closed with `ChatBridgeError`. Error messages name the
missing variable, never its value, so endpoints and tokens do not leak into
logs.

## Python API

```python
from templeos import chat_bridge

chat_bridge.reply(text)        # -> str, raises ChatBridgeError on failure
chat_bridge.try_reply(text)    # -> str | None (None means "use the fallback")
chat_bridge.get_bridge()       # cached ChatBridge built from the environment
chat_bridge.reset_bridge()     # forget the cached bridge after config changes
chat_bridge.build_bridge(config=None, transport=None)  # explicit construction
```

Errors:

- `ChatBridgeDisabled` — `TEMPLEOS_CHAT_BRIDGE` is off.
- `ChatBridgeUnavailable` — enabled but no endpoint, no transport, unreachable
  agent, empty reply, or oversized reply.
- `ChatBridgeError` — invalid text, endpoint, timeout, or another contract
  violation. The two classes above subclass it.

`ChatBridge.reply` validates that the relay supplies a non-empty string,
forwards that exact text, and returns the agent's non-empty string. A
transport supplied by the host (for a loopback socket it already owns) is a
callable `text -> reply` and requires no endpoint.

## Built-in HTTP wire contract

Request:

```
POST <TEMPLEOS_CHAT_BRIDGE_ENDPOINT>
Content-Type: application/json
Accept: application/json, text/plain
Authorization: Bearer <token>        # only when TEMPLEOS_CHAT_BRIDGE_TOKEN is set

{"text": "<finished relay reply>"}
```

Accepted responses (HTTP 2xx):

- `{"reply": "..."}`
- `{"text": "..."}`
- `{"message": "..."}`
- a JSON string, e.g. `"..."` (the quotes are part of the JSON)
- a plain-text body

An empty body, an empty/blank string, a non-2xx status, an unreachable
endpoint, or a reply over 2 MiB is `ChatBridgeUnavailable`. The request body
is capped by the host relay, not by this module.

## Relay wiring (INT)

`ChatResponder.reply(text)` is the only required call site. Keep the existing
offline responder as the fallback:

```python
from templeos import chat_bridge
from hermes_chat_relay import HermesResponder

class ChatResponder:
    def __init__(self):
        self.offline = HermesResponder()

    def reply(self, text: str) -> str:
        bridge = chat_bridge.get_bridge()
        if not bridge.available():
            return self.offline.reply(text)
        try:
            return bridge.reply(text)
        except chat_bridge.ChatBridgeError:
            return self.offline.reply(text)
```

Set `TEMPLEOS_CHAT_BRIDGE=1` and the endpoint/token in the host's own config
provider. Do not pass them on a command line, and do not write them into the
plugin data directory. When the bridge is disabled, the relay behaves exactly
as it does today.

## Tests

`tests/test_chat_bridge.py` is fully offline:

- default-disabled path raises `ChatBridgeDisabled`; `try_reply` returns `None`;
- enabled-without-agent path raises a clear `ChatBridgeUnavailable`;
- a fake transport proves the exact text is forwarded and the answer returned;
- the module entrypoint reads the environment;
- the token is absent from `repr` and from error messages;
- an unreachable loopback port is unavailable without echoing the endpoint;
- invalid endpoint/timeout/text fail closed;
- the real HTTP transport round-trips against an ephemeral loopback server,
  including the bearer header, plain-text replies, and empty-reply rejection;
- `TOOL_NAMES` is still exactly four and contains no chat tool.

## Non-goals

- No fifth Hermes tool, no schema change.
- No VPS, deployment, tunnel, BBS hostname, or credential provisioning.
- No transcript storage; the host relay remains the source of truth.
- No invented replies: unavailable always means the relay's fallback.
