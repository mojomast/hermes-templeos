from __future__ import annotations

import hashlib
import os
import struct
import time
from pathlib import Path

import pytest

from templeos import diskimage, flavors, qemu, vm
from templeos.flavors import DEFAULT, get_flavor
from tests.fakes import FakeQMP, FakeSerial

BAKEOFF_ISO = Path("/workspace/templeos-bakeoff/isos/TinkerOS_5.20-rc10.ISO")
TINKER_SHA = get_flavor("tinkeros")["sha256"]


class FakeProc:
    def __init__(self, pid: int = 987654) -> None:
        self.pid = pid
        self._code: int | None = None

    def poll(self) -> int | None:
        return self._code

    def terminate(self) -> None:
        self._code = 0

    def kill(self) -> None:
        self._code = 9

    def wait(self, timeout: float | None = None) -> int:
        if self._code is None:
            self._code = 0
        return self._code


@pytest.fixture
def vm_clean(tos_home):
    yield tos_home
    try:
        vm.stop()
    finally:
        vm._runtime = None


def _pin_iso(tos_home: Path, monkeypatch: pytest.MonkeyPatch, flavor: str | None = None, payload: bytes = b"iso") -> Path:
    flavor = flavor or DEFAULT
    rec = get_flavor(flavor)
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(flavors.FLAVORS[flavor], "sha256", digest)
    monkeypatch.setitem(flavors.FLAVORS[flavor], "bytes", len(payload))
    path = tos_home / "isos" / rec["iso_filename"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _wire(monkeypatch: pytest.MonkeyPatch, qmp: FakeQMP | None = None, serial: FakeSerial | None = None, proc: FakeProc | None = None):
    qmp = qmp or FakeQMP()
    serial = serial or FakeSerial()
    proc = proc or FakeProc()
    captured: dict = {}

    def fake_spawn(argv, *, env, cwd=None, log_path=None):
        captured["argv"] = list(argv)
        captured["env"] = dict(env)
        captured["cwd"] = cwd
        captured["log_path"] = log_path
        return proc

    monkeypatch.setattr(vm, "qmp_factory", lambda: qmp)
    monkeypatch.setattr(vm, "serial_factory", lambda: serial)
    monkeypatch.setattr(vm, "spawn", fake_spawn)
    return qmp, serial, proc, captured


def test_status_when_stopped(vm_clean):
    body = vm.status()
    assert body["ok"] is True
    assert body["running"] is False
    assert body["pid"] is None
    assert body["flavor"] == "templeoh"
    assert body["sockets"] == {"qmp": False, "vnc": False, "com1": False}
    assert set(body["sockets"]) == {"qmp", "vnc", "com1"}
    assert all(isinstance(v, bool) for v in body["sockets"].values())


def test_start_stop_reset_and_argv(vm_clean, monkeypatch):
    _pin_iso(vm_clean, monkeypatch, flavor="tinkeros")
    qmp, serial, proc, captured = _wire(monkeypatch)
    body = vm.start(flavor="tinkeros")
    assert body["ok"] is True
    assert body["running"] is True
    assert body["flavor"] == "tinkeros"
    assert body["accel"] in ("tcg", "kvm")
    assert body["pid"] == proc.pid
    assert serial.connected is True
    assert qmp.connected is True
    argv = captured["argv"]
    assert "-nic" in argv and argv[argv.index("-nic") + 1] == "none"
    assert "ORBIT_TOKEN" not in captured["env"]
    assert (vm_clean / "qemu.pid").read_text().strip() == str(proc.pid)
    assert (vm_clean / "disks" / "tinkeros.qcow2").is_file()
    again = vm.start(flavor="tinkeros")
    assert again["ok"] is True and again["running"] is True
    assert again["pid"] == proc.pid
    assert again.get("attached") is not True
    reset = vm.reset()
    assert reset["ok"] is True
    assert any(cmd[0] == "system_reset" for cmd in qmp.commands)
    stopped = vm.stop()
    assert stopped["ok"] is True and stopped["running"] is False
    assert not qemu.is_running(proc)
    assert not (vm_clean / "qemu.pid").exists()


def test_start_reattaches_after_runtime_drop(vm_clean, monkeypatch):
    """A gateway restart drops _runtime but leaves QEMU running; start must rebind."""
    _pin_iso(vm_clean, monkeypatch, flavor="tinkeros")
    qmp, serial, proc, _captured = _wire(monkeypatch)
    body = vm.start(flavor="tinkeros")
    assert body["ok"] is True and body["running"] is True

    from templeos.paths import socket_paths
    from templeos.screen import get_runtime, unbind

    socks = socket_paths(vm_clean)
    socks["qmp"].parent.mkdir(parents=True, exist_ok=True)
    for path in socks.values():
        if not path.exists():
            path.write_bytes(b"")

    vm._runtime = None
    unbind()
    monkeypatch.setattr(vm, "_pid_is_qemu", lambda pid: pid == proc.pid)
    monkeypatch.setattr(vm, "_pid_alive", lambda pid: pid == proc.pid)

    qmp2, serial2 = FakeQMP(), FakeSerial()
    monkeypatch.setattr(vm, "qmp_factory", lambda: qmp2)
    monkeypatch.setattr(vm, "serial_factory", lambda: serial2)
    attached = vm.start(flavor="tinkeros")
    assert attached["ok"] is True
    assert attached["running"] is True
    assert attached.get("attached") is True
    assert attached["pid"] == proc.pid
    assert qmp2.connected is True
    assert serial2.connected is True
    assert get_runtime() is not None
    assert vm.get_runtime() is not None


def test_start_boots_verified_disk_overlay_without_iso(vm_clean, monkeypatch):
    payload = b"verified-preinstalled-disk"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(diskimage, "DISK_SHA256", digest)
    monkeypatch.setattr(diskimage, "DISK_BYTES", len(payload))
    image = vm_clean / diskimage.DISK_FILENAME
    image.write_bytes(payload)
    diskimage.save_config(disk_image="on", disk_image_path=str(image))
    overlay = vm_clean / "disks" / "templeoh-disk-overlay.qcow2"

    def fake_overlay(base, dest=None, **kwargs):
        target = Path(dest) if dest is not None else overlay
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"qcow2-overlay")
        return target

    monkeypatch.setattr(diskimage, "ensure_overlay", fake_overlay)
    qmp, serial, proc, captured = _wire(monkeypatch)
    body = vm.start(flavor="templeoh")
    assert body["ok"] is True and body["running"] is True
    argv = captured["argv"]
    assert "-cdrom" not in argv
    assert argv[argv.index("-boot") + 1].startswith("order=c")
    assert any(str(overlay) in part for part in argv)
    assert vm.current().boot_from_disk is True
    assert vm.current().disk == overlay
    assert serial.connected is True and qmp.connected is True
    # The pinned base is never modified; only the overlay exists.
    assert image.read_bytes() == payload
    assert overlay.is_file()


def test_start_falls_back_to_live_iso_when_disk_download_fails(vm_clean, monkeypatch):
    diskimage.save_config(disk_image="on")
    _pin_iso(vm_clean, monkeypatch, flavor="templeoh")
    _qmp, _serial, _proc, captured = _wire(monkeypatch)
    body = vm.start(flavor="templeoh")
    assert body["ok"] is True and body["running"] is True
    argv = captured["argv"]
    assert "-cdrom" in argv
    assert vm.current().boot_from_disk is False


def test_start_without_iso_is_iso_missing(vm_clean, monkeypatch):
    _wire(monkeypatch)
    body = vm.start()
    assert body["ok"] is False
    assert body["code"] == "iso_missing"


def test_stale_pidfile_is_cleaned(vm_clean, monkeypatch):
    _pin_iso(vm_clean, monkeypatch)
    _wire(monkeypatch)
    (vm_clean / "qemu.pid").write_text("1\n")  # pid 1 is not qemu-system-x86_64
    (vm_clean / "sockets").mkdir(parents=True, exist_ok=True)
    leftover = vm_clean / "sockets" / "qmp.sock"
    leftover.write_text("stale")
    body = vm.start()
    assert body["ok"] is True
    assert body["running"] is True


def test_snapshot_ejects_floppy_then_savevm(vm_clean, monkeypatch):
    _pin_iso(vm_clean, monkeypatch)
    qmp, _serial, _proc, _cap = _wire(monkeypatch, qmp=FakeQMP(floppy_writable=True))
    assert vm.start()["ok"] is True
    body = vm.snapshot("golden")
    assert body["ok"] is True
    assert body["snapshot"] == "golden"
    assert any(line.startswith("eject") for line in qmp.hmp_lines)
    assert any(line.startswith("savevm golden") for line in qmp.hmp_lines)
    assert "golden" in qmp.snapshots


def test_restore_sends_cont_on_success_and_failure(vm_clean, monkeypatch):
    _pin_iso(vm_clean, monkeypatch)
    qmp, _serial, _proc, _cap = _wire(monkeypatch)
    assert vm.start()["ok"] is True
    ok = vm.restore("golden")
    assert ok["ok"] is True
    assert ok["snapshot"] == "golden"
    assert qmp.paused is False
    assert "loadvm golden" in qmp.hmp_lines
    assert any(line.strip() == "cont" for line in qmp.hmp_lines)

    qmp.fail_loadvm = True
    failed = vm.restore("golden")
    assert failed["ok"] is False and failed["code"] == "restore_failed"
    assert qmp.paused is False  # cont was issued after the failed loadvm


def test_start_loads_golden_when_present(vm_clean, monkeypatch):
    _pin_iso(vm_clean, monkeypatch, flavor="tinkeros")
    qmp, _serial, _proc, _cap = _wire(monkeypatch)
    monkeypatch.setattr(vm, "list_snapshots", lambda disk: ["golden"])
    body = vm.start(flavor="tinkeros", snapshot="golden")
    assert body["ok"] is True
    assert body["snapshot"] == "golden"
    assert "loadvm golden" in qmp.hmp_lines
    assert qmp.paused is False


def test_snapshot_and_restore_require_a_running_vm(vm_clean):
    assert vm.snapshot()["code"] == "vm_not_running"
    assert vm.restore()["code"] == "vm_not_running"
    assert vm.reset()["code"] == "vm_not_running"


def test_rejects_bad_snapshot_name(vm_clean, monkeypatch):
    _pin_iso(vm_clean, monkeypatch)
    _wire(monkeypatch)
    assert vm.start()["ok"] is True
    assert vm.snapshot("../etc/passwd")["code"] == "invalid_args"
    assert vm.restore("foo/bar")["code"] == "invalid_args"


def test_status_socket_flags_are_booleans_not_paths(vm_clean, monkeypatch):
    _pin_iso(vm_clean, monkeypatch)
    _wire(monkeypatch)
    vm.start()
    # Fake spawn does not create unix sockets; flags must still be booleans.
    flags = vm.status()["sockets"]
    assert set(flags) == {"qmp", "vnc", "com1"}
    assert all(isinstance(v, bool) for v in flags.values())
    # Never leak a path or token-looking string.
    blob = str(vm.status())
    assert "sk-" not in blob
    assert "ORBIT_TOKEN" not in blob


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _smoke_ready() -> bool:
    return os.environ.get("TEMPLEOS_SMOKE") == "1" and BAKEOFF_ISO.is_file()


@pytest.mark.smoke
def test_tinkeros_boot_snapshot_restore_stop(tmp_path, monkeypatch):
    if not _smoke_ready():
        pytest.skip("set TEMPLEOS_SMOKE=1 and keep the pinned TinkerOS ISO on disk")
    digest = hashlib.sha256(BAKEOFF_ISO.read_bytes()).hexdigest()
    assert digest == TINKER_SHA, "bake-off ISO does not match the pinned SHA-256"

    home = tmp_path / "tos-home"
    home.mkdir()
    monkeypatch.setenv("TEMPLEOS_HOME", str(home))
    vm._runtime = None

    cache = home / "isos"
    cache.mkdir(parents=True)
    link = cache / get_flavor("tinkeros")["iso_filename"]
    try:
        link.symlink_to(BAKEOFF_ISO)
    except OSError:
        import shutil

        shutil.copy2(BAKEOFF_ISO, link)

    procs_before = _qemu_pids()
    started = None
    try:
        started = vm.start(flavor="tinkeros")
        assert started["ok"] is True, started
        assert started["running"] is True
        assert started["accel"] == "tcg"
        qmp = vm.current().qmp
        ready = _wait_desktop(qmp, home / "frames", timeout_s=120)
        assert ready["ok"], f"TinkerOS did not reach a desktop prompt: {ready}"
        qmp.send_key(["n"])
        time.sleep(1.0)
        qmp.send_key(["n"])
        time.sleep(2.0)
        prompt = home / "frames" / "prompt.png"
        qmp.screendump(prompt)
        width, height = _png_size(prompt)
        assert (width, height) == (640, 480)
        assert prompt.stat().st_size > 8000

        snapped = vm.snapshot("golden")
        assert snapped["ok"] is True, snapped
        restored = vm.restore("golden")
        assert restored["ok"] is True, restored
        assert vm.status()["running"] is True
        after = home / "frames" / "restored.png"
        qmp.screendump(after)
        assert _png_size(after) == (640, 480)
    finally:
        try:
            vm.stop()
        except Exception:
            pass
        vm._runtime = None
        leftover = _qemu_pids() - procs_before
        for pid in leftover:
            _kill(pid)
        still = _qemu_pids() - procs_before
        assert not still, f"leaked QEMU pids: {still}"


def _wait_desktop(qmp, frame_dir: Path, timeout_s: float) -> dict:
    frame_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    last = None
    n = 0
    while time.monotonic() - t0 < timeout_s:
        n += 1
        dest = frame_dir / f"boot-{n:03d}.png"
        qmp.screendump(dest)
        elapsed = time.monotonic() - t0
        try:
            width, height = _png_size(dest)
        except Exception:
            time.sleep(1.0)
            continue
        size = dest.stat().st_size
        last = {"t": round(elapsed, 2), "width": width, "height": height, "bytes": size, "path": str(dest)}
        # Require a settled colorful 640x480 frame; ignore mid-boot flashes
        # in the first few seconds (the ZealOS bake-off false-started at 4s).
        if elapsed >= 8 and width == 640 and height == 480 and size > 8000:
            return {"ok": True, **last}
        time.sleep(1.0)
    return {"ok": False, "last": last}


def _qemu_pids() -> set[int]:
    found: set[int] = set()
    proc = Path("/proc")
    if not proc.is_dir():
        return found
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmd = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if b"qemu-system-x86_64" in cmd:
            found.add(int(entry.name))
    return found


def _kill(pid: int) -> None:
    try:
        os.kill(pid, 15)
    except OSError:
        return
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)
    try:
        os.kill(pid, 9)
    except OSError:
        return


def test_start_error_includes_qemu_log_tail_when_child_already_exited(vm_clean, monkeypatch):
    _pin_iso(vm_clean, monkeypatch, flavor="tinkeros")
    proc = FakeProc()
    proc._code = 1

    def fake_spawn(argv, *, env, cwd=None, log_path=None):
        assert log_path is not None
        log_path.write_text(
            "qemu-system-x86_64: -drive file=disk.qcow2,if=ide,index=0: duplicate index\n"
            f"log path was {log_path}\n"
        )
        return proc

    monkeypatch.setattr(vm, "spawn", fake_spawn)
    body = vm.start(flavor="tinkeros")
    assert body["ok"] is False
    assert body["code"] == "qemu_start_failed"
    assert "duplicate index" in body["error"]
    assert "QMP connect failed" not in body["error"]
    assert str(vm_clean) not in body["error"]
