from __future__ import annotations

import pytest

from templeos.api import (
    ROUTE_CONTROL,
    ROUTE_FRAME,
    ROUTE_HEALTH,
    ROUTE_INPUT,
    ROUTE_STATUS,
    frame_payload,
    health_payload,
    set_control,
    status_payload,
    user_input,
)
from templeos.arbiter import reset_arbiter


def test_health_and_control_are_implemented(tos_home):
    reset_arbiter()
    health = health_payload()
    assert health["ok"] is True
    assert health["plugin"] == "templeos"
    assert health["version"] == "0.1.0"
    assert health["mode"] == "shared"
    taken = set_control({"op": "take"})
    assert taken["ok"] is True and taken["mode"] == "user" and taken["agent_paused"] is True
    back = set_control({"mode": "shared"})
    assert back["mode"] == "shared"
    watch = set_control({"op": "watch"})
    assert watch["user_may_input"] is False


def test_status_and_frame_are_not_implemented_but_shaped(tos_home):
    reset_arbiter()
    status = status_payload()
    assert status["code"] == "not_implemented"
    assert status["running"] is False
    assert status["mode"] == "shared"
    assert set(status["sockets"]) == {"qmp", "vnc", "com1"}
    frame = frame_payload()
    assert frame["ok"] is False and frame["code"] == "not_implemented"
    assert frame.get("mime") == "image/png"


def test_user_input_records_hold_off_and_watch_only(tos_home):
    reset_arbiter()
    set_control({"op": "watch"})
    body = user_input({"type": "key", "text": "a"})
    assert body["code"] == "watch_only"
    set_control({"op": "handback"})
    body = user_input({"type": "click", "x": 10, "y": 20})
    assert body["code"] == "not_implemented"
    assert body["agent_paused"] is True


def test_router_mounts_when_fastapi_is_available():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from templeos.api import create_router
    from templeos.arbiter import reset_arbiter

    reset_arbiter()
    app = FastAPI()
    app.include_router(create_router())
    client = TestClient(app)
    health = client.get(ROUTE_HEALTH).json()
    assert health["ok"] is True
    assert client.get(ROUTE_STATUS).json()["code"] == "not_implemented"
    assert client.get(ROUTE_FRAME).json()["code"] == "not_implemented"
    taken = client.post(ROUTE_CONTROL, json={"op": "take"}).json()
    assert taken["mode"] == "user"
    got = client.get(ROUTE_CONTROL).json()
    assert got["mode"] == "user"
    client.post(ROUTE_CONTROL, json={"op": "handback"})
    typo = client.post(ROUTE_INPUT, json={"type": "click", "x": 1, "y": 2}).json()
    assert typo["code"] == "not_implemented"


@pytest.mark.smoke
def test_live_qemu_smoke_is_skipped_unless_requested():
    pytest.skip("Slice 0 has no live QEMU smoke; set TEMPLEOS_SMOKE=1 in later slices.")
