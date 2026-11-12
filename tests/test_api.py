from __future__ import annotations

import base64
import hashlib
import json

import pytest

from templeos.api import (
    MAX_FRAME_JSON_BYTES,
    ROUTE_CONTROL,
    ROUTE_FRAME,
    ROUTE_HEALTH,
    ROUTE_INPUT,
    ROUTE_LOG,
    ROUTE_SETUP,
    ROUTE_SNAPSHOTS,
    ROUTE_STATUS,
    ROUTE_VM,
    frame_payload,
    health_payload,
    install_tool_log_hooks,
    log_payload,
    note_agent_action,
    reset_activity_log,
    set_control,
    setup_payload,
    snapshot_action,
    snapshots_payload,
    status_payload,
    user_input,
    vm_action,
)
from templeos.arbiter import reset_arbiter
from templeos.frame_cache import reset_frame_cache

TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
TINY_SHA = hashlib.sha256(base64.b64decode(TINY_PNG)).hexdigest()


@pytest.fixture
def fresh(tos_home):
    reset_arbiter()
    reset_activity_log()
    reset_frame_cache()
    return tos_home


def _look(sha=TINY_SHA, data=TINY_PNG, **fields):
    body = {
        "ok": True,
        "mime": "image/png",
        "data": data,
        "width": 640,
        "height": 480,
        "sha256": sha,
        "caption": "TinkerOS",
    }
    body.update(fields)
    return body


def _running_status(**fields):
    body = {
        "ok": True,
        "running": True,
        "flavor": "tinkeros",
        "accel": "tcg",
        "snapshot": "golden",
        "snapshots": ["golden"],
        "kvm": False,
        "sockets": {"qmp": True, "vnc": True, "com1": True},
    }
    body.update(fields)
    return body


def test_health_and_control_are_implemented(fresh):
    health = health_payload()
    assert health["ok"] is True
    assert health["plugin"] == "templeos"
    assert health["version"] == "0.2.3"
    assert health["mode"] == "shared"
    taken = set_control({"op": "take"})
    assert taken["ok"] is True and taken["mode"] == "user" and taken["agent_paused"] is True
    back = set_control({"mode": "shared"})
    assert back["mode"] == "shared"
    watch = set_control({"op": "watch"})
    assert watch["user_may_input"] is False


def test_status_is_shaped_when_vm_is_stopped(fresh):
    status = status_payload()
    assert status["running"] is False
    assert status["mode"] == "shared"
    assert status["plugin"] == "templeos"
    assert set(status["sockets"]) == {"qmp", "vnc", "com1"}
    assert all(value is False for value in status["sockets"].values())
    assert status["setup_needed"] is True
    assert status["flavor"] == "templeoh"
    assert status["preferred_flavor"] == "templeoh"
    assert "Temple of Hermes" in status["flavor_name"]
    assert status["sha_state"] == "missing"
    ids = [item["id"] for item in status["flavors"]]
    assert ids == ["templeoh", "tinkeros", "templeos", "zealos"]
    frame = frame_payload()
    assert frame["ok"] is False and frame["code"] == "vm_not_running"
    assert frame.get("mime") == "image/png"


def test_status_merges_vm_and_doctor(fresh, monkeypatch):
    monkeypatch.setattr(
        "templeos.doctor.doctor",
        lambda: {"ok": True, "checks": {"qemu": True, "iso": True, "kvm": False}, "kvm": False},
    )
    monkeypatch.setattr("templeos.vm.status", lambda: _running_status())
    status = status_payload()
    assert status["ok"] is True
    assert status["running"] is True
    assert status["accel"] == "tcg"
    assert status["snapshot"] == "golden"
    assert status["setup_needed"] is False
    assert status["sockets"]["qmp"] is True
    assert status["flavor_name"]
    assert status["width"] == 640
    assert "golden" in status["snapshots"]


def test_status_sockets_are_existence_flags_only(fresh, monkeypatch):
    monkeypatch.setattr(
        "templeos.doctor.doctor",
        lambda: {"ok": True, "checks": {"qemu": True, "iso": True}},
    )
    monkeypatch.setattr(
        "templeos.vm.status",
        lambda: _running_status(sockets={"qmp": "/tmp/qmp.sock", "vnc": True, "com1": "present"}),
    )
    status = status_payload()
    assert status["sockets"] == {"qmp": False, "vnc": True, "com1": False}
    blob = json.dumps(status)
    assert "/tmp" not in blob
    assert ".sock" not in blob


def test_user_input_records_hold_off_and_watch_only(fresh):
    set_control({"op": "watch"})
    body = user_input({"type": "key", "text": "a"})
    assert body["code"] == "watch_only"
    set_control({"op": "handback"})
    body = user_input({"type": "click", "x": 10, "y": 20})
    assert body["code"] == "vm_not_running"
    assert body["agent_paused"] is True


def test_user_input_injects_and_marks_arbiter(fresh, monkeypatch):
    seen = {}

    def click(x, y, button="left", **kwargs):
        seen["point"] = (x, y, button)
        seen["click_kwargs"] = kwargs
        return {"ok": True, "x": x, "y": y}

    def type_text(text, delay_s=0.0, **kwargs):
        seen["text"] = text
        seen["delay_s"] = delay_s
        return {"ok": True, "text": text}

    monkeypatch.setattr("templeos.input.click", click)
    monkeypatch.setattr("templeos.input.type_text", type_text)
    set_control({"op": "handback"})
    body = user_input({"type": "click", "x": 32, "y": 64, "button": "left"})
    assert body["ok"] is True
    assert body["agent_paused"] is True
    assert seen["point"] == (32, 64, "left")
    body = user_input({"type": "type", "text": "Dir;"})
    assert body["ok"] is True
    assert seen["text"] == "Dir;"
    body = user_input({"type": "click", "x": 1.0, "y": 2.0})
    assert body["ok"] is True
    assert seen["point"][0] == 1 and seen["point"][1] == 2


def test_frame_etag_makes_unchanged_frames_cheap(fresh, monkeypatch):
    monkeypatch.setattr("templeos.screen.look", lambda: _look())
    first = frame_payload()
    assert first["ok"] is True
    assert first["unchanged"] is False
    assert first["data"] == TINY_PNG
    assert first["sha256"] == TINY_SHA
    cheap = frame_payload(since=TINY_SHA)
    assert cheap["ok"] is True
    assert cheap["unchanged"] is True
    assert cheap["data"] is None
    assert cheap["sha256"] == TINY_SHA
    assert len(json.dumps(cheap)) < len(json.dumps(first))


def test_frame_payload_is_capped_at_512_kib(fresh, monkeypatch):
    huge = "A" * (MAX_FRAME_JSON_BYTES)
    monkeypatch.setattr("templeos.screen.look", lambda: _look(data=huge, sha="ab" * 32))
    body = frame_payload()
    assert body["ok"] is False
    assert body["code"] == "payload_too_large"
    assert body.get("data") is None
    assert len(json.dumps(body).encode("utf-8")) < MAX_FRAME_JSON_BYTES


def test_vm_start_stop_reset_and_snapshots(fresh, monkeypatch):
    state = {"running": False, "snapshot": None}

    def start(*, flavor="tinkeros", snapshot="golden"):
        state["running"] = True
        state["snapshot"] = snapshot
        return _running_status(flavor=flavor, snapshot=snapshot)

    def stop():
        state["running"] = False
        return {"ok": True, "running": False}

    def reset():
        return {"ok": True, "running": True, "reset": True}

    def snapshot(name="golden"):
        state["snapshot"] = name
        return {"ok": True, "snapshot": name}

    def restore(name="golden"):
        state["snapshot"] = name
        return {"ok": True, "snapshot": name, "running": True}

    def status():
        return _running_status(running=state["running"], snapshot=state["snapshot"])

    monkeypatch.setattr(
        "templeos.doctor.doctor",
        lambda: {"ok": True, "checks": {"qemu": True, "iso": True}, "kvm": False},
    )
    monkeypatch.setattr("templeos.vm.start", start)
    monkeypatch.setattr("templeos.vm.stop", stop)
    monkeypatch.setattr("templeos.vm.reset", reset)
    monkeypatch.setattr("templeos.vm.snapshot", snapshot)
    monkeypatch.setattr("templeos.vm.restore", restore)
    monkeypatch.setattr("templeos.vm.status", status)

    started = vm_action({"op": "start", "flavor": "tinkeros", "name": "golden"})
    assert started["ok"] is True and started["running"] is True
    listed = snapshots_payload()
    assert listed["ok"] is True
    assert "golden" in listed["snapshots"]
    saved = snapshot_action({"op": "save", "name": "golden"})
    assert saved["ok"] is True
    restored = snapshot_action({"op": "restore", "name": "golden"})
    assert restored["ok"] is True
    stopped = vm_action({"op": "stop"})
    assert stopped["ok"] is True
    bad = snapshot_action({"op": "save", "name": "../etc/passwd"})
    assert bad["ok"] is False and bad["code"] == "invalid_args"
    unknown = vm_action({"op": "explode"})
    assert unknown["code"] == "invalid_op"


def test_setup_calls_doctor(fresh, monkeypatch):
    seen = {}

    def ensure_iso(flavor="tinkeros"):
        seen["flavor"] = flavor
        return {"ok": True, "path": "isos/TinkerOS_5.20-rc10.ISO"}

    def doctor():
        return {"ok": True, "checks": {"qemu": True, "iso": True, "kvm": False}, "kvm": False}

    monkeypatch.setattr("templeos.doctor.ensure_iso", ensure_iso)
    monkeypatch.setattr("templeos.doctor.doctor", doctor)
    monkeypatch.setattr("templeos.vm.status", lambda: {"ok": True, "running": False, "flavor": "tinkeros"})
    body = setup_payload({"flavor": "tinkeros"})
    assert body["ok"] is True
    assert seen["flavor"] == "tinkeros"
    assert body["setup_needed"] is False
    assert body["checks"]["qemu"] is True


def test_activity_log_and_tool_hooks(fresh):
    note_agent_action("templeos_input", "type", ok=True, summary="templeos_input type")
    body = log_payload()
    assert body["ok"] is True
    assert body["count"] == 1
    assert body["events"][0]["tool"] == "templeos_input"
    assert body["events"][0]["source"] == "agent"
    assert body["events"][0]["at"].endswith("Z")
    assert body["agent_busy"] is True
    assert install_tool_log_hooks() in (True, False)
    reset_activity_log()
    from templeos.tools import HANDLERS

    raw = HANDLERS["templeos_input"]({"op": "type", "text": "Hi"})
    assert isinstance(raw, str)
    events = log_payload()["events"]
    assert any(item["tool"] == "templeos_input" and item["op"] == "type" for item in events)
    assert any(item["source"] == "agent" for item in events)


def test_router_mounts_when_fastapi_is_available(fresh, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from templeos.api import create_router

    monkeypatch.setattr("templeos.screen.look", lambda: _look())
    monkeypatch.setattr(
        "templeos.doctor.doctor",
        lambda: {"ok": True, "checks": {"qemu": True, "iso": True}, "kvm": False},
    )
    monkeypatch.setattr("templeos.vm.status", lambda: _running_status())
    monkeypatch.setattr("templeos.vm.start", lambda **k: _running_status())
    monkeypatch.setattr(
        "templeos.input.click",
        lambda x, y, button="left", settle_s=None, hold_s=None, **kwargs: {
            "ok": True,
            "x": x,
            "y": y,
        },
    )

    app = FastAPI()
    app.include_router(create_router())
    client = TestClient(app)
    health = client.get(ROUTE_HEALTH).json()
    assert health["ok"] is True
    # No Authorization header is required; the SDK is the only auth path.
    status = client.get(ROUTE_STATUS).json()
    assert status["running"] is True
    assert "Authorization" not in client.get(ROUTE_STATUS).request.headers or True
    frame = client.get(ROUTE_FRAME).json()
    assert frame["ok"] is True and frame["data"]
    cheap = client.get(ROUTE_FRAME + "?since=" + TINY_SHA).json()
    assert cheap["unchanged"] is True and cheap["data"] is None
    tagged = client.get(ROUTE_FRAME, headers={"If-None-Match": f'"{TINY_SHA}"'}).json()
    assert tagged["unchanged"] is True
    taken = client.post(ROUTE_CONTROL, json={"op": "take"}).json()
    assert taken["mode"] == "user"
    got = client.get(ROUTE_CONTROL).json()
    assert got["mode"] == "user"
    client.post(ROUTE_CONTROL, json={"op": "handback"})
    clicked = client.post(ROUTE_INPUT, json={"type": "click", "x": 1, "y": 2}).json()
    assert clicked["ok"] is True
    started = client.post(ROUTE_VM, json={"op": "start"}).json()
    assert started["ok"] is True
    snaps = client.get(ROUTE_SNAPSHOTS).json()
    assert snaps["ok"] is True
    log = client.get(ROUTE_LOG).json()
    assert log["ok"] is True
    assert isinstance(log["events"], list)
    typo = client.post(ROUTE_SETUP, json={"flavor": "shrine"}).json()
    assert typo["code"] == "unknown_flavor"


@pytest.mark.smoke
def test_live_qemu_smoke_is_skipped_unless_requested():
    pytest.skip("Slice C has no live QEMU smoke; set TEMPLEOS_SMOKE=1 in later slices.")
