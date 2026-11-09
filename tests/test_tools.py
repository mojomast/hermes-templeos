from __future__ import annotations

import json

from templeos.arbiter import Arbiter, reset_arbiter
from templeos.tools import (
    SCHEMA_FILES,
    SCHEMA_INPUT,
    SCHEMA_SCREEN,
    SCHEMA_VM,
    handle_files,
    handle_input,
    handle_screen,
    handle_vm,
    tool_specs,
)


def _parse(raw: str) -> dict:
    assert isinstance(raw, str)
    body = json.loads(raw)
    assert "ok" in body and "error" in body and "code" in body and "fix" in body
    return body


def test_schemas_have_tight_ops():
    assert SCHEMA_VM["parameters"]["required"] == ["op"]
    assert SCHEMA_VM["parameters"]["additionalProperties"] is False
    names = [s["name"] for s in tool_specs()]
    assert names == ["templeos_vm", "templeos_screen", "templeos_input", "templeos_files"]
    for schema in (SCHEMA_VM, SCHEMA_SCREEN, SCHEMA_INPUT, SCHEMA_FILES):
        assert schema["parameters"]["additionalProperties"] is False


def test_unknown_flavor_and_snapshot_name(tos_home):
    body = _parse(handle_vm({"op": "start", "flavor": "shrine"}))
    assert body["ok"] is False and body["code"] == "unknown_flavor"
    body = _parse(handle_vm({"op": "snapshot", "name": "../etc/passwd"}))
    assert body["ok"] is False and body["code"] == "invalid_args"


def test_ops_without_a_running_vm_return_structured_errors(tos_home):
    start = _parse(handle_vm({"op": "start", "flavor": "tinkeros"}))
    assert start["ok"] is False
    assert start["code"] in {"iso_missing", "qemu_missing", "doctor_failed"}
    assert start["fix"]

    doctor = _parse(handle_vm({"op": "doctor"}))
    assert "ok" in doctor and doctor["code"] in {None, "doctor_failed", "iso_missing", "qemu_missing"}
    assert doctor["fix"] or doctor["ok"] is True

    look = _parse(handle_screen({"op": "look"}))
    assert look["ok"] is False and look["code"] == "vm_not_running"
    text = _parse(handle_screen({"op": "read_text"}))
    assert text["ok"] is False and text["code"] == "vm_not_running"

    typed = _parse(handle_input({"op": "type", "text": "Hi"}))
    assert typed["ok"] is False and typed["code"] == "vm_not_running"

    listed = _parse(handle_files({"op": "list", "path": "T:/"}))
    assert listed["ok"] is False and listed["code"] == "serial_not_ready"
    assert listed["fix"]


def test_input_is_paused_in_user_mode(tos_home):
    reset_arbiter(Arbiter())
    get = __import__("templeos.arbiter", fromlist=["get_arbiter"]).get_arbiter()
    get.take_control()
    body = _parse(handle_input({"op": "type", "text": "Hi"}))
    assert body["ok"] is False and body["code"] == "agent_paused"
    assert "Hand back" in body["fix"]


def test_files_confinement(tos_home, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    body = _parse(handle_files({"op": "pull", "path": "T:/Home/X.HC", "dest": str(outside)}))
    assert body["ok"] is False and body["code"] == "path_escape"
    body = _parse(handle_files({"op": "push", "path": "T:/Home/X.HC", "src": str(outside)}))
    assert body["ok"] is False and body["code"] == "path_escape"
    dest = tos_home / "inbox" / "X.HC"
    dest.parent.mkdir()
    body = _parse(handle_files({"op": "pull", "path": "T:/Home/X.HC", "dest": str(dest)}))
    assert body["code"] == "serial_not_ready"


def test_type_requires_text_and_holyc_has_a_cap(tos_home):
    body = _parse(handle_input({"op": "type"}))
    assert body["code"] == "invalid_args"
    body = _parse(handle_input({"op": "holyc", "text": "x" * (64 * 1024 + 1)}))
    assert body["code"] == "invalid_args"
    body = _parse(handle_input({"op": "click", "x": "1", "y": 2}))
    assert body["code"] == "invalid_args"
