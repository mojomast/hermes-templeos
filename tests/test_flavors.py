from __future__ import annotations

import pytest

from templeos.flavors import (
    DEFAULT,
    FLAVOR_IDS,
    FlavorError,
    assert_airgap,
    disk_args,
    get_flavor,
    machine_args,
    socket_args,
)
from pathlib import Path


TOH_URL = "https://github.com/mojomast/temple-of-hermes/releases/download/v0.1.3/TempleOfHermes-0.1.3.ISO"
TOH_SHA = "fbaa3d6f0a8f9190f295e933c32cb833a61b3cb43a708309acb6c98ff51ac4fd"
TOH_BYTES = 14_053_376


def test_default_is_templeoh_and_pins_are_64_hex():
    assert DEFAULT == "templeoh"
    assert FLAVOR_IDS == ("templeoh", "tinkeros", "templeos", "zealos")
    rec = get_flavor()
    assert rec["id"] == "templeoh"
    assert rec["name"] == "Temple of Hermes 0.1.3"
    assert rec["default"] is True
    assert rec["url"] == TOH_URL
    assert rec["sha256"] == TOH_SHA
    assert rec["bytes"] == TOH_BYTES
    assert rec["iso_filename"] == "TempleOfHermes-0.1.3.ISO"
    assert rec["width"] == 640 and rec["height"] == 480
    assert rec["mouse"] == "vmmouse" and rec["serial"] == "comm" and rec["bus"] == "ide"
    assert get_flavor("temple-of-hermes")["id"] == "templeoh"
    assert get_flavor("temple_of_hermes")["id"] == "templeoh"
    # Other official flavors stay selectable and are no longer the default.
    for fid in ("tinkeros", "templeos", "zealos"):
        item = get_flavor(fid)
        assert item["id"] == fid
        assert item["default"] is False
    for fid in FLAVOR_IDS:
        item = get_flavor(fid)
        assert len(item["sha256"]) == 64
        assert set(item["sha256"]) <= set("0123456789abcdef")
        assert item["url"].startswith("https://")
        assert "raw/main" not in item["url"]
        assert isinstance(item["bytes"], int) and item["bytes"] > 0
    zeal = get_flavor("zealos")
    assert zeal["bus"] == "ahci" and zeal["width"] == 1024
    tink = get_flavor("tinkeros")
    assert tink["sha256"] == "feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4"
    with pytest.raises(FlavorError):
        get_flavor("shrine")


def test_machine_args_are_airgapped():
    argv = ["qemu-system-x86_64", *machine_args(accel="tcg")]
    assert "-nic" in argv and argv[argv.index("-nic") + 1] == "none"
    assert "-machine" in argv and "kernel-irqchip=off" in argv[argv.index("-machine") + 1]
    assert "-accel" in argv and argv[argv.index("-accel") + 1] == "tcg"
    assert_airgap(argv)
    with pytest.raises(FlavorError):
        assert_airgap(["qemu-system-x86_64", "-netdev", "user,id=n0"])
    with pytest.raises(FlavorError):
        machine_args(accel="whp")


def test_disk_args_boots_verified_overlay_without_cdrom(tmp_path):
    iso = tmp_path / "cd.iso"
    overlay = tmp_path / "templeoh-disk-overlay.qcow2"
    args = disk_args("templeoh", iso, overlay, boot_from_disk=True)
    assert "-cdrom" not in args
    assert args[args.index("-boot") + 1].startswith("order=c")
    drive = args[args.index("-drive") + 1]
    assert str(overlay) in drive
    assert "format=qcow2" in drive
    assert "if=ide" in drive and "media=disk" in drive
    # Other flavors keep their live-ISO path even if the flag is passed.
    zeal = disk_args("zealos", iso, overlay, boot_from_disk=True)
    assert "-cdrom" not in zeal
    assert "ahci,id=ahci" in zeal


def test_disk_and_socket_args(tmp_path):
    iso = tmp_path / "cd.iso"
    disk = tmp_path / "d.qcow2"
    iso.write_bytes(b"x")
    disk.write_bytes(b"y")
    ide = disk_args("tinkeros", iso, disk)
    assert "-cdrom" in ide and str(iso) in ide
    assert any("if=ide" in part for part in ide)
    ahci = disk_args("zealos", iso, disk)
    assert "ahci,id=ahci" in ahci
    assert any(part.startswith("-device") or "ide-cd" in part for part in ahci)
    assert "-cdrom" not in ahci
    qmp, vnc, com = tmp_path / "qmp.sock", tmp_path / "vnc.sock", tmp_path / "com1.sock"
    socks = socket_args(qmp=qmp, vnc=vnc, com1=com)
    joined = " ".join(socks)
    assert "unix:" in joined and "server=on" in joined
    assert "tcp:" not in joined and ":5900" not in joined
