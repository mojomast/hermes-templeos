"""Terry companion observers, status shape, and atlas envelope."""

from __future__ import annotations

import base64
from pathlib import Path

import yaml

from templeos import companion
from templeos.companion import HOOK_NAMES
from templeos.api import status_payload
from tests.fakes import FakeCtx

ROOT = Path(__file__).resolve().parents[1]


def setup_function(_fn=None):
    companion.reset_state()


def test_hooks_declared_match_registration():
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    assert sorted(manifest["provides_hooks"]) == sorted(HOOK_NAMES)
    ctx = FakeCtx()
    registered = companion.register_hooks(ctx)
    assert sorted(registered) == sorted(HOOK_NAMES)
    assert sorted(ctx.hooks) == sorted(HOOK_NAMES)


def test_enabled_by_default_and_env_off(monkeypatch):
    assert companion.companion_enabled() is True
    monkeypatch.setenv("TEMPLEOS_COMPANION", "off")
    assert companion.companion_enabled() is False
    monkeypatch.setenv("TEMPLEOS_COMPANION", "terry")
    assert companion.companion_enabled() is True


def test_state_mapping_tool_and_stream():
    hooks = companion._make_hooks()
    hooks["pre_llm_call"]()
    assert companion.resolve_animation() == "waiting"
    hooks["post_llm_call"]()
    hooks["pre_tool_call"]()
    assert companion.resolve_animation() == "running"
    hooks["post_tool_call"](ok=True)
    assert companion.resolve_animation() == "jumping"
    companion.reset_state()
    hooks["pre_tool_call"]()
    hooks["post_tool_call"](ok=False)
    assert companion.resolve_animation() == "failed"
    companion.reset_state()
    hooks["on_human_input_request"]()
    assert companion.resolve_animation() == "review"
    hooks["on_session_start"]()
    # review sticky wins over waving
    assert companion.resolve_animation() == "review"
    hooks["on_human_input_resolved"]()
    companion.reset_state()
    companion.note_vm_booting(True)
    assert companion.resolve_animation() in {"running-right", "running-left"}


def test_status_payload_includes_companion(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMPLEOS_HOME", str(tmp_path))
    body = status_payload()
    assert "companion" in body
    assert body["companion"]["character"] == "terry"
    assert body["companion"]["enabled"] is True
    assert body["companion"]["tribute"] is True
    assert "No official" in body["companion"]["attribution"]


def test_atlas_payload_base64_and_contained():
    body = companion.atlas_payload("base")
    assert body["ok"] is True
    assert body["mime"] == "image/png"
    raw = base64.b64decode(body["data"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert body["atlas"]["width"] == 1536
    assert body["atlas"]["height"] == 1872
    names = [row["name"] for row in body["atlas"]["rows"]]
    assert names == [
        "idle",
        "running-right",
        "running-left",
        "waving",
        "jumping",
        "failed",
        "waiting",
        "running",
        "review",
    ]
    for costume in ("cowboy", "wizard", "chef"):
        other = companion.atlas_payload(costume)
        assert other["ok"] is True
        assert other["costume"] == costume


def test_atlas_respects_off_switch(monkeypatch):
    monkeypatch.setenv("TEMPLEOS_COMPANION", "off")
    body = companion.atlas_payload("base")
    assert body["ok"] is False
    assert body["code"] == "companion_off"
