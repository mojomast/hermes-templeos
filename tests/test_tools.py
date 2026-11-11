from __future__ import annotations

import json

from templeos.arbiter import Arbiter, reset_arbiter
from templeos.tools import (
    FILES_OPS_ALL,
    RPC_METHODS,
    SCHEMA_FILES,
    SCHEMA_INPUT,
    SCHEMA_SCREEN,
    SCHEMA_VM,
    SCREEN_OPS,
    VM_OPS,
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


def test_p3_ops_are_advertised_on_the_four_tools():
    assert len(tool_specs()) == 4
    assert SCHEMA_VM["parameters"]["properties"]["op"]["enum"] == list(VM_OPS)
    assert SCHEMA_SCREEN["parameters"]["properties"]["op"]["enum"] == list(SCREEN_OPS)
    assert SCHEMA_FILES["parameters"]["properties"]["op"]["enum"] == list(FILES_OPS_ALL)
    assert SCHEMA_FILES["parameters"]["properties"]["method"]["enum"] == list(RPC_METHODS)
    assert "modem" in VM_OPS
    assert "lore" in SCREEN_OPS
    assert "rpc" in FILES_OPS_ALL


def test_modem_op_reports_a_serial_modem_and_keeps_the_nic_off(tos_home):
    from templeos.flavors import (
        assert_airgap,
        modem_profile,
        set_modem_enabled,
        socket_args,
    )
    from pathlib import Path

    set_modem_enabled(False)
    try:
        off = _parse(handle_vm({"op": "modem", "mode": "status"}))
        assert off["ok"] is True
        assert off["modem"] == "off"
        assert off["transport"] == "serial"
        assert off["com"] == 2
        assert off["network"] == "off"
        assert str(tos_home) not in json.dumps(off)

        on = _parse(handle_vm({"op": "modem", "mode": "on"}))
        assert on["ok"] is True
        assert on["enabled"] is True
        assert modem_profile("tinkeros")["modem"] == "on"

        socks = socket_args(
            qmp=Path(tos_home) / "qmp.sock",
            vnc=Path(tos_home) / "vnc.sock",
            com1=Path(tos_home) / "com1.sock",
        )
        joined = " ".join(socks)
        assert "modem.sock" in joined
        assert "-nic none" not in joined  # machine_args still owns the airgap
        assert "tcp:" not in joined
        assert_airgap(["qemu-system-x86_64", "-nic", "none", *socks])

        cleared = _parse(handle_vm({"op": "modem", "mode": "off"}))
        assert cleared["ok"] is True
        assert cleared["enabled"] is False
        assert "modem.sock" not in " ".join(
            socket_args(
                qmp=Path(tos_home) / "qmp.sock",
                vnc=Path(tos_home) / "vnc.sock",
                com1=Path(tos_home) / "com1.sock",
            )
        )
    finally:
        set_modem_enabled(False)


def test_modem_op_rejects_an_unknown_mode(tos_home):
    body = _parse(handle_vm({"op": "modem", "mode": "dial"}))
    assert body["ok"] is False and body["code"] == "invalid_args"


def test_lore_op_returns_static_operator_notes(tos_home):
    body = _parse(handle_screen({"op": "lore"}))
    assert body["ok"] is True
    assert body["topic"] == "templeos-operator"
    assert "T:/Home>" in body["text"]
    assert "CommInit" in body["text"]
    assert "G2;" in body["text"]


def test_files_rpc_uses_the_guest_daemon_and_structures_errors(tos_home):
    from templeos import files as files_mod
    from tests.fakes import FakeSerial

    files_mod.bind_serial(None)
    missing = _parse(handle_files({"op": "rpc", "method": "ping"}))
    assert missing["ok"] is False and missing["code"] == "serial_not_ready"

    port = FakeSerial()
    port.open(tos_home / "com1.sock")
    files_mod.bind_serial(port)
    try:
        entries = [{"name": "X.HC", "size": 12}]
        payload = json.dumps(entries).encode("utf-8")
        port.rx.extend(files_mod.encode_frame(files_mod.CMD_LIST_OK, payload))
        ping = _parse(handle_files({"op": "rpc", "method": "ping", "path": "T:/Home/"}))
        assert ping["ok"] is True
        assert ping["method"] == "ping"
        assert ping["count"] == 1
        assert ping["protocol"] == files_mod.PROTO_VERSION
        assert "elapsed_ms" in ping

        port.rx.extend(files_mod.encode_frame(files_mod.CMD_LIST_OK, payload))
        stat = _parse(handle_files({"op": "rpc", "method": "stat", "path": "T:/Home/"}))
        assert stat["ok"] is True
        assert stat["count"] == 1
        assert stat["entries"] == entries

        port.rx.extend(files_mod.encode_frame(files_mod.CMD_LIST_OK, payload))
        version = _parse(handle_files({"op": "rpc", "method": "version"}))
        assert version["ok"] is True
        assert version["magic"] == "TXFR"
        assert version["max_file_bytes"] == files_mod.MAX_FILE_BYTES
    finally:
        files_mod.bind_serial(None)

    bad = _parse(handle_files({"op": "rpc", "method": "explode"}))
    assert bad["ok"] is False and bad["code"] == "invalid_args"


def test_community_ops_return_structured_errors_without_a_guest(tos_home, monkeypatch):
    for name in (
        "TOH_BBS_ENABLED",
        "TOH_BBS_ENDPOINT",
        "TOH_BBS_SERVER_NAME",
        "TOH_BBS_CA_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    summary = _parse(handle_vm({"op": "session_start"}))
    assert summary["ok"] is False
    assert summary["code"] == "session_unavailable"
    assert "data" not in summary
    digest = _parse(handle_vm({"op": "bbs_digest"}))
    assert digest["ok"] is False
    assert digest["code"] == "bbs_not_configured"
    missing = _parse(handle_files({"op": "codeshare_fetch"}))
    assert missing["code"] == "invalid_args"
    fetch = _parse(handle_files({"op": "codeshare_fetch", "id": "post_1"}))
    assert fetch["ok"] is False
    assert fetch["code"] == "bbs_not_configured"


def test_still_exactly_four_tools_with_community_ops():
    names = [s["name"] for s in tool_specs()]
    assert names == ["templeos_vm", "templeos_screen", "templeos_input", "templeos_files"]
    assert "session_start" in VM_OPS and "bbs_digest" in VM_OPS
    assert "codeshare_fetch" in FILES_OPS_ALL
    assert SCHEMA_VM["parameters"]["properties"]["op"]["enum"] == list(VM_OPS)
    assert SCHEMA_FILES["parameters"]["properties"]["op"]["enum"] == list(FILES_OPS_ALL)
