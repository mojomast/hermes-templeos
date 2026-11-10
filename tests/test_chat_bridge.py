"""Offline tests for the plugin-side chat bridge.

No host agent, network, or credentials are involved: the HTTP transport tests
use a loopback server bound to an ephemeral port, and every other test injects
a fake transport. The bridge must never invent a reply.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from templeos import chat_bridge
from templeos.chat_bridge import (
    ChatBridge,
    ChatBridgeConfig,
    ChatBridgeDisabled,
    ChatBridgeError,
    ChatBridgeUnavailable,
    build_bridge,
)
from templeos.tools import TOOL_NAMES


class _Recorder:
    def __init__(self, answer: str = "agent says hi") -> None:
        self.answer = answer
        self.calls: list[str] = []

    def __call__(self, text: str) -> str:
        self.calls.append(text)
        return self.answer


@pytest.fixture(autouse=True)
def _reset_default_bridge():
    chat_bridge.reset_bridge()
    yield
    chat_bridge.reset_bridge()


def _clean_env(monkeypatch) -> None:
    for name in (
        chat_bridge.ENV_ENABLED,
        chat_bridge.ENV_ENDPOINT,
        chat_bridge.ENV_TOKEN,
        chat_bridge.ENV_TIMEOUT,
    ):
        monkeypatch.delenv(name, raising=False)


def test_bridge_is_disabled_by_default(monkeypatch):
    _clean_env(monkeypatch)
    assert ChatBridgeConfig.from_env().enabled is False
    with pytest.raises(ChatBridgeDisabled):
        chat_bridge.reply("hello")
    assert chat_bridge.try_reply("hello") is None


def test_enabled_without_an_agent_is_a_clear_unavailable_error(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv(chat_bridge.ENV_ENABLED, "1")
    bridge = chat_bridge.get_bridge()
    assert bridge.enabled is True
    assert bridge.available() is False
    with pytest.raises(ChatBridgeUnavailable) as caught:
        bridge.reply("hello")
    assert "no agent endpoint" in str(caught.value)
    assert bridge.try_reply("hello") is None


def test_reply_forwards_the_text_and_returns_the_agent_answer():
    recorder = _Recorder("42")
    bridge = ChatBridge(ChatBridgeConfig(enabled=True), transport=recorder)
    assert bridge.reply('"Hello from Hermes\\n"; 6*7;') == "42"
    assert recorder.calls == ['"Hello from Hermes\\n"; 6*7;']
    assert bridge.available() is True


def test_module_entrypoint_uses_env_enabled_bridge(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv(chat_bridge.ENV_ENABLED, "true")
    monkeypatch.setenv(chat_bridge.ENV_ENDPOINT, "http://127.0.0.1:9/agent")
    recorder = _Recorder("relay reply")
    monkeypatch.setattr(chat_bridge, "_http_transport", lambda config: recorder)
    assert chat_bridge.reply("host relay text") == "relay reply"
    assert recorder.calls == ["host relay text"]


def test_token_stays_out_of_repr_and_error_messages(monkeypatch):
    secret = "unit-test-token-not-real"
    config = ChatBridgeConfig.from_env(
        {
            chat_bridge.ENV_ENABLED: "1",
            chat_bridge.ENV_ENDPOINT: "http://127.0.0.1:9/agent",
            chat_bridge.ENV_TOKEN: secret,
        }
    )
    assert secret not in repr(config)
    recorder = _Recorder("ok")
    assert ChatBridge(config, transport=recorder).reply("hi") == "ok"


def test_unreachable_agent_is_unavailable_without_leaking_the_endpoint():
    endpoint = "http://127.0.0.1:1/agent"
    bridge = ChatBridge(ChatBridgeConfig(enabled=True, endpoint=endpoint, timeout_s=1.0))
    with pytest.raises(ChatBridgeUnavailable) as caught:
        bridge.reply("hi")
    assert endpoint not in str(caught.value)
    assert "unreachable" in str(caught.value)


def test_bad_configuration_is_rejected():
    with pytest.raises(ChatBridgeError):
        ChatBridgeConfig.from_env({chat_bridge.ENV_ENDPOINT: "ftp://example.invalid/x"})
    with pytest.raises(ChatBridgeError):
        ChatBridgeConfig.from_env({chat_bridge.ENV_TIMEOUT: "not-a-number"})
    with pytest.raises(ChatBridgeError):
        ChatBridgeConfig.from_env({chat_bridge.ENV_TIMEOUT: "-1"})
    bridge = ChatBridge(ChatBridgeConfig(enabled=True), transport=_Recorder())
    with pytest.raises(ChatBridgeError):
        bridge.reply("   ")


class _AgentHandler(BaseHTTPRequestHandler):
    payload = {"reply": "Hello from Hermes"}
    seen: list[dict] = []
    seen_auth: list[str | None] = []

    def do_POST(self):  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        _AgentHandler.seen.append(json.loads(raw.decode("utf-8")))
        _AgentHandler.seen_auth.append(self.headers.get("Authorization"))
        body = json.dumps(_AgentHandler.payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep pytest output quiet
        return


@pytest.fixture
def loopback_agent():
    _AgentHandler.seen = []
    _AgentHandler.seen_auth = []
    _AgentHandler.payload = {"reply": "Hello from Hermes"}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AgentHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}/agent"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_transport_round_trips_over_loopback(loopback_agent):
    token = "unit-test-token-not-real"
    bridge = build_bridge(
        ChatBridgeConfig(enabled=True, endpoint=loopback_agent, token=token, timeout_s=5.0)
    )
    assert bridge.reply("say hello") == "Hello from Hermes"
    assert _AgentHandler.seen == [{"text": "say hello"}]
    assert _AgentHandler.seen_auth == [f"Bearer {token}"]


def test_http_transport_accepts_plain_text_and_rejects_empty(loopback_agent):
    _AgentHandler.payload = "plain reply"
    bridge = build_bridge(
        ChatBridgeConfig(enabled=True, endpoint=loopback_agent, timeout_s=5.0)
    )
    assert bridge.reply("hi") == "plain reply"

    _AgentHandler.payload = {"reply": ""}
    with pytest.raises(ChatBridgeUnavailable):
        bridge.reply("hi")


def test_bridge_adds_no_fifth_tool():
    assert len(TOOL_NAMES) == 4
    assert "templeos_chat" not in TOOL_NAMES
    assert "chat_bridge" not in TOOL_NAMES
