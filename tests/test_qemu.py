from __future__ import annotations

import os
import subprocess
from pathlib import Path

from templeos.envsafe import child_env
from templeos.flavors import assert_airgap, get_flavor
from templeos import qemu


def test_build_argv_tinkeros_and_templeos_are_ide_and_airgapped(tmp_path):
    iso = tmp_path / "TinkerOS_5.20-rc10.ISO"
    disk = tmp_path / "tinkeros.qcow2"
    iso.write_bytes(b"iso")
    disk.write_bytes(b"disk")
    qmp, vnc, com1 = tmp_path / "qmp.sock", tmp_path / "vnc.sock", tmp_path / "com1.sock"
    for flavor in ("tinkeros", "templeos"):
        argv = qemu.build_argv(
            flavor=flavor,
            iso=iso,
            disk=disk,
            qmp=qmp,
            vnc=vnc,
            com1=com1,
            accel="tcg",
            name=f"templeos-{flavor}",
        )
        assert argv[0].endswith("qemu-system-x86_64") or Path(argv[0]).name == "qemu-system-x86_64"
        assert "-nic" in argv and argv[argv.index("-nic") + 1] == "none"
        assert "-machine" in argv and "kernel-irqchip=off" in argv[argv.index("-machine") + 1]
        assert "-accel" in argv and argv[argv.index("-accel") + 1] == "tcg"
        assert "-cpu" in argv and argv[argv.index("-cpu") + 1] == "qemu64"
        assert "-m" in argv and argv[argv.index("-m") + 1] == "2G"
        assert "-display" in argv and argv[argv.index("-display") + 1] == "none"
        assert "-cdrom" in argv
        assert any("if=ide" in part and "qcow2" in part for part in argv)
        assert any(part.startswith("unix:") and "server=on" in part for part in argv)
        assert not any(part.startswith("tcp:") for part in argv)
        assert "usb-tablet" not in " ".join(argv)
        assert "virtio" not in " ".join(argv)
        assert_airgap(argv)


def test_build_argv_disk_boot_attaches_overlay_and_no_cdrom(tmp_path):
    iso = tmp_path / "TempleOfHermes-0.1.2.ISO"
    overlay = tmp_path / "templeoh-disk-overlay.qcow2"
    overlay.write_bytes(b"qcow2")
    argv = qemu.build_argv(
        flavor="templeoh",
        iso=iso,
        disk=overlay,
        qmp=tmp_path / "qmp.sock",
        vnc=tmp_path / "vnc.sock",
        com1=tmp_path / "com1.sock",
        accel="tcg",
        name="templeos-templeoh",
        boot_from_disk=True,
    )
    assert "-cdrom" not in argv
    assert argv[argv.index("-boot") + 1].startswith("order=c")
    assert any("if=ide" in part and "qcow2" in part and str(overlay) in part for part in argv)
    assert_airgap(argv)


def test_build_argv_zealos_uses_ahci_not_cdrom(tmp_path):
    iso = tmp_path / get_flavor("zealos")["iso_filename"]
    disk = tmp_path / "zealos.qcow2"
    iso.write_bytes(b"iso")
    disk.write_bytes(b"disk")
    argv = qemu.build_argv(
        flavor="zealos",
        iso=iso,
        disk=disk,
        qmp=tmp_path / "qmp.sock",
        vnc=tmp_path / "vnc.sock",
        com1=tmp_path / "com1.sock",
        accel="kvm",
        name="templeos-zealos",
    )
    assert "-accel" in argv and argv[argv.index("-accel") + 1] == "kvm"
    assert "-cdrom" not in argv
    assert "ahci,id=ahci" in argv
    assert any("ide-cd" in part or part == "ide-cd,drive=cdrom,bus=ahci.0,bootindex=1" for part in argv)
    assert_airgap(argv)


def test_spawn_uses_allowlist_and_terminate_stops_child(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBIT_TOKEN", "should-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")
    monkeypatch.setenv("NODE_OPTIONS", "--require leak")
    captured: dict[str, dict[str, str]] = {}
    real = subprocess.Popen

    def wrapped(*args, **kwargs):
        captured["env"] = kwargs["env"]
        assert kwargs.get("start_new_session") is True
        return real(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", wrapped)
    proc = qemu.spawn(["/bin/sleep", "60"], env=child_env(), log_path=tmp_path / "qemu.log")
    try:
        assert qemu.is_running(proc)
        env = captured["env"]
        assert "ORBIT_TOKEN" not in env
        assert "OPENAI_API_KEY" not in env
        assert "NODE_OPTIONS" not in env
        assert "PATH" in env
        assert "LANG" in env
    finally:
        qemu.terminate(proc, timeout_s=2.0)
    assert not qemu.is_running(proc)
    assert proc.poll() is not None


def test_is_running_and_terminate_are_null_safe():
    assert qemu.is_running(None) is False
    qemu.terminate(None)


def test_create_disk_and_list_snapshots(tmp_path):
    if qemu.find_binary("qemu-img") is None:
        return
    disk = tmp_path / "guest.qcow2"
    created = qemu.create_disk(disk, "8M")
    assert created.is_file()
    # Second call must not clobber an existing image.
    first_stat = created.stat()
    qemu.create_disk(disk, "8M")
    assert created.stat().st_size == first_stat.st_size
    assert qemu.list_snapshots(disk) == []
    assert qemu.list_snapshots(tmp_path / "missing.qcow2") == []


def test_find_binary_locates_qemu():
    path = qemu.find_binary()
    assert path is not None
    assert path.name == "qemu-system-x86_64"
    assert os.access(path, os.X_OK)
