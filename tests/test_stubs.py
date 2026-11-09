from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from templeos import doctor, files, input as tos_input, qemu, qmp, screen, serial, vm


def test_stub_modules_raise_not_implemented(tos_home):
    calls = [
        lambda: qemu.build_argv(
            flavor="tinkeros",
            iso=tos_home / "isos" / "x.iso",
            disk=tos_home / "disks" / "x.qcow2",
            qmp=tos_home / "sockets" / "qmp.sock",
            vnc=tos_home / "sockets" / "vnc.sock",
            com1=tos_home / "sockets" / "com1.sock",
        ),
        lambda: qemu.spawn(["qemu-system-x86_64"], env={"PATH": "/bin"}),
        lambda: qemu.terminate(None),
        lambda: qemu.is_running(None),
        lambda: qmp.QMPClient().connect(tos_home / "sockets" / "qmp.sock"),
        lambda: qmp.QMPClient().close(),
        lambda: qmp.QMPClient().cmd("query-status"),
        lambda: qmp.QMPClient().hmp("info status"),
        lambda: qmp.QMPClient().screendump(tos_home / "frames" / "a.png"),
        lambda: qmp.QMPClient().send_key(["ret"]),
        lambda: qmp.QMPClient().input_send_event([]),
        lambda: serial.SerialPort().open(tos_home / "sockets" / "com1.sock"),
        lambda: serial.SerialPort().close(),
        lambda: serial.SerialPort().write(b"A"),
        lambda: serial.SerialPort().read(),
        lambda: serial.SerialPort().read_available(),
        lambda: vm.start(),
        lambda: vm.stop(),
        lambda: vm.reset(),
        lambda: vm.snapshot(),
        lambda: vm.restore(),
        lambda: vm.status(),
        lambda: doctor.kvm_usable(),
        lambda: doctor.qemu_version(),
        lambda: doctor.ensure_iso(),
        lambda: doctor.doctor(),
        lambda: screen.look(),
        lambda: screen.read_text(),
        lambda: screen.wait_idle(),
        lambda: screen.frame_hash(),
        lambda: screen.glyph_read(b""),
        lambda: tos_input.type_text("Hi"),
        lambda: tos_input.send_keys(["ret"]),
        lambda: tos_input.click(1, 2),
        lambda: tos_input.move(1, 2),
        lambda: tos_input.holyc("Dir;"),
        lambda: files.list_guest(),
        lambda: files.pull("T:/X.HC", tos_home / "X.HC"),
        lambda: files.push(tos_home / "X.HC", "T:/X.HC"),
    ]
    for fn in calls:
        with pytest.raises(NotImplementedError, match="Slice "):
            fn()


def test_stub_signatures_are_documented():
    for fn in (
        qemu.build_argv,
        vm.start,
        vm.restore,
        screen.look,
        tos_input.click,
        tos_input.holyc,
        doctor.kvm_usable,
        files.pull,
    ):
        assert inspect.getdoc(fn)
        assert "Slice " in (inspect.getdoc(fn) or "") or fn.__module__.startswith("templeos.")
