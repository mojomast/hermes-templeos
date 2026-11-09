from __future__ import annotations

import pytest

from tests.fakes import MIN_PNG, FakeQMP, FakeSerial


def test_fake_qmp_screendump_and_keys(tmp_path):
    qmp = FakeQMP()
    qmp.connect(tmp_path / "qmp.sock")
    dest = tmp_path / "frame.png"
    qmp.screendump(dest)
    assert dest.read_bytes() == MIN_PNG
    qmp.send_key(["shift", "h"])
    assert qmp.keys[-1] == ["shift", "h"]


def test_fake_qmp_abs_mouse_and_snapshot_pitfalls(tmp_path):
    missing = FakeQMP(abs_mouse=False)
    missing.connect(tmp_path / "qmp.sock")
    with pytest.raises(RuntimeError, match="input handler not found"):
        missing.input_send_event([{"type": "abs", "data": {"axis": "x", "value": 1}}])
    floppy = FakeQMP(floppy_writable=True)
    floppy.connect(tmp_path / "qmp.sock")
    with pytest.raises(RuntimeError, match="snapshots"):
        floppy.hmp("savevm golden")
    floppy.hmp("eject floppy0")
    floppy.hmp("savevm golden")
    assert "golden" in floppy.snapshots
    loader = FakeQMP()
    loader.connect(tmp_path / "qmp.sock")
    loader.fail_loadvm = True
    with pytest.raises(RuntimeError, match="loadvm"):
        loader.hmp("loadvm golden")
    assert loader.paused is True
    loader.hmp("cont")
    assert loader.paused is False


def test_fake_serial_drops_bytes_until_open():
    port = FakeSerial()
    port.guest_write(b"AZXYZ")
    assert port.dropped == b"AZXYZ"
    assert port.rx == b""
    port.open("/tmp/com1.sock")
    port.guest_write(b"A")
    assert port.read_available() == b"A"
    port.write(b"xyz")
    assert port.tx == b"xyz"
    port.close()
    with pytest.raises(RuntimeError):
        port.write(b"z")
