from __future__ import annotations

import inspect
import json

from templeos import doctor, files, input as tos_input, qemu, qmp, screen, serial, vm
from templeos.tools import handle_files, handle_input, handle_screen, handle_vm


def test_public_apis_are_implemented_and_documented(tos_home):
    """Slice stubs are gone: public functions exist, are callable, and have docs."""
    for fn in (
        qemu.build_argv,
        qemu.spawn,
        qemu.terminate,
        qemu.is_running,
        qmp.QMPClient.connect,
        qmp.QMPClient.close,
        qmp.QMPClient.cmd,
        qmp.QMPClient.hmp,
        qmp.QMPClient.screendump,
        qmp.QMPClient.send_key,
        qmp.QMPClient.input_send_event,
        serial.SerialPort.open,
        serial.SerialPort.close,
        serial.SerialPort.write,
        serial.SerialPort.read,
        serial.SerialPort.read_available,
        vm.start,
        vm.stop,
        vm.reset,
        vm.snapshot,
        vm.restore,
        vm.status,
        vm.get_runtime,
        vm.get_serial,
        doctor.kvm_usable,
        doctor.qemu_version,
        doctor.ensure_iso,
        doctor.doctor,
        screen.look,
        screen.read_text,
        screen.wait_idle,
        screen.frame_hash,
        screen.glyph_read,
        tos_input.type_text,
        tos_input.send_keys,
        tos_input.click,
        tos_input.move,
        tos_input.holyc,
        files.list_guest,
        files.pull,
        files.push,
    ):
        assert callable(fn)
        assert inspect.getdoc(fn)


def test_unbound_ops_return_structured_errors_not_stubs(tos_home):
    """No public op raises NotImplementedError('Slice ...') after integration."""
    status = vm.status()
    assert status["ok"] is True
    assert status["running"] is False
    assert vm.get_runtime() is None
    assert vm.get_serial() is None

    started = vm.start()
    assert started["ok"] is False
    assert started["code"] in {"iso_missing", "qemu_missing", "doctor_failed"}

    reset = vm.reset()
    assert reset["ok"] is False and reset["code"] == "vm_not_running"

    look = screen.look()
    assert look["ok"] is False and look["code"] == "vm_not_running"
    read = screen.read_text()
    assert read["ok"] is False and read["code"] == "vm_not_running"
    hashed = screen.frame_hash()
    assert hashed["ok"] is False and hashed["code"] == "vm_not_running"

    typed = tos_input.type_text("Hi")
    assert typed["ok"] is False and typed["code"] == "vm_not_running"
    clicked = tos_input.click(1, 2)
    assert clicked["ok"] is False and clicked["code"] == "vm_not_running"

    listed = files.list_guest("T:/")
    assert listed["ok"] is False and listed["code"] == "serial_not_ready"

    try:
        screen.glyph_read(b"")
        raise AssertionError("glyph_read(b'') should reject empty bytes")
    except ValueError:
        pass


def test_tool_handlers_without_a_vm_are_structured(tos_home):
    def parse(raw):
        assert isinstance(raw, str)
        body = json.loads(raw)
        assert set(body) >= {"ok", "error", "code", "fix"}
        return body

    start = parse(handle_vm({"op": "start", "flavor": "tinkeros"}))
    assert start["ok"] is False
    assert start["code"] in {"iso_missing", "qemu_missing", "doctor_failed"}

    look = parse(handle_screen({"op": "look"}))
    assert look["ok"] is False and look["code"] == "vm_not_running"

    typed = parse(handle_input({"op": "type", "text": "Hi"}))
    assert typed["ok"] is False and typed["code"] == "vm_not_running"

    listed = parse(handle_files({"op": "list", "path": "T:/"}))
    assert listed["ok"] is False and listed["code"] == "serial_not_ready"

    status = parse(handle_vm({"op": "status"}))
    assert status["ok"] is True and status["running"] is False
