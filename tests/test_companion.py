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
    assert companion.resolve_animation() == "typing"
    hooks["post_tool_call"](ok=True)
    assert companion.resolve_animation() == "celebrate_short"
    companion.reset_state()
    hooks["pre_tool_call"]()
    hooks["post_tool_call"](ok=True)
    # Second success alternates onto the atlas jump row.
    hooks["pre_tool_call"]()
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
    assert companion.resolve_animation() == "nod"
    companion.reset_state()
    hooks["on_session_start"]()
    assert companion.resolve_animation() == "greet"
    companion.reset_state()
    companion.note_vm_booting(True)
    assert companion.resolve_animation() == "vm_booting"
    hooks["on_stream_start"]()
    # Boot takes priority over talking.
    assert companion.resolve_animation() == "vm_booting"
    companion.note_vm_running()
    assert companion.resolve_animation() == "talking"


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


def test_relieved_after_failed_recovers():
    hooks = companion._make_hooks()
    hooks["post_tool_call"](ok=False)
    assert companion.resolve_animation() == "failed"
    with companion._LOCK:
        companion._STATE["until"] = 0.0
    assert companion.resolve_animation() == "relieved"


def test_say_bubble_and_clip_payloads():
    snap = companion.say("Hello from the pane")
    assert snap["active"] is True
    assert snap["text"] == "Hello from the pane"
    body = companion.snapshot()
    assert body["speech"]["text"] == "Hello from the pane"
    companion.clear_speech()
    assert companion.snapshot()["speech"]["active"] is False

    denied = companion.clip_payload("../atlas")
    assert denied["ok"] is False

    manifest = companion.clips_manifest()
    assert manifest["ok"] is True
    names = [c["name"] for c in manifest["manifest"]["clips"]]
    assert names == list(companion.RICH_CLIPS)
    clip = companion.clip_payload("typing")
    assert clip["ok"] is True
    raw = base64.b64decode(clip["data"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert clip["clip"]["cell"] == [192, 208]
    assert clip["clip"]["loop"] is True


def test_clip_respects_off_switch(monkeypatch):
    monkeypatch.setenv("TEMPLEOS_COMPANION", "off")
    assert companion.clips_manifest()["code"] == "companion_off"
    assert companion.clip_payload("dance")["code"] == "companion_off"


def test_config_companion_off_and_hide_toggle(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMPLEOS_HOME", str(tmp_path))
    monkeypatch.delenv("TEMPLEOS_COMPANION", raising=False)
    ctx = FakeCtx()
    ctx.config = {"companion": "off"}
    assert companion.apply_config(ctx) is False
    assert companion.companion_enabled() is False
    assert companion.atlas_payload("base")["code"] == "companion_off"

    # The pane Hide Terry toggle is independent of the off switch: it only
    # conceals the sprite and persists through the plugin data dir.
    assert companion.set_hidden(True) is True
    assert companion.snapshot()["hidden"] is True
    assert companion.set_hidden(False) is False
    assert companion.snapshot()["hidden"] is False

    # The env switch wins over the config file.
    monkeypatch.setenv("TEMPLEOS_COMPANION", "terry")
    assert companion.companion_enabled() is True


def test_prefs_reload_after_restart_and_config_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMPLEOS_HOME", str(tmp_path))
    monkeypatch.delenv("TEMPLEOS_COMPANION", raising=False)
    companion.set_hidden(True)
    companion.set_costume("wizard")
    companion.reset_state()  # simulate a fresh process state
    assert companion.snapshot()["hidden"] is False

    ctx = FakeCtx()
    companion.register_hooks(ctx)
    snap = companion.snapshot()
    assert snap["hidden"] is True
    assert snap["costume"] == "wizard"

    # An explicit companion: off config still wins over the persisted prefs.
    companion.reset_state()
    ctx_off = FakeCtx()
    ctx_off.config = {"companion": "off"}
    companion.register_hooks(ctx_off)
    assert companion.companion_enabled() is False
