"""Pinned guest flavors, ISO URLs/hashes, and proven QEMU flag fragments.

Hashes and launch flags come from the 9 Nov 2026 bake-off in
/workspace/templeos-bakeoff. Network is always off. QEMU itself is never bundled.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

DEFAULT = "tinkeros"
FLAVOR_IDS = ("tinkeros", "templeos", "zealos")

# Shared machine shape proven under TCG (and intended for KVM when /dev/kvm opens).
MACHINE = "pc,kernel-irqchip=off"
CPU = "qemu64"
MEMORY = "2G"
SMP = "1"
VGA = "std"
QEMU_BINARY = "qemu-system-x86_64"
QEMU_IMG = "qemu-img"
DISK_SIZE = "2G"

FLAVORS: dict[str, dict[str, Any]] = {
    "tinkeros": {
        "id": "tinkeros",
        "name": "TinkerOS 5.20-rc10",
        "default": True,
        "iso_filename": "TinkerOS_5.20-rc10.ISO",
        "url": "https://github.com/tinkeros/TinkerOS/releases/download/5.20-rc10/TinkerOS_5.20-rc10.ISO",
        "sha256": "feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4",
        "md5": "b82c8d9bba2ddb904ae51fc998d2557d",
        "bytes": 35_487_744,
        "width": 640,
        "height": 480,
        "bus": "ide",
        "mouse": "vmmouse",
        "serial": "comm",
        # Crop the title-bar clock/FPS and the System Keys chrome for stable hashes.
        "hash_crop": {"x": 0, "y": 24, "w": 520, "h": 446},
    },
    "templeos": {
        "id": "templeos",
        "name": "TempleOS 5.03",
        "default": False,
        "iso_filename": "TOS_Distro.ISO",
        "url": "https://templeos.org/Downloads/TOS_Distro.ISO",
        "sha256": "3c68ca395d0b64f779f1ffa330e2685798b17862e3c36ae4e349537fd676b40b",
        "md5": "bc0a9310776e536ad52c68df558cfdc1",
        "bytes": 17_346_560,
        "width": 640,
        "height": 480,
        "bus": "ide",
        "mouse": "msset",
        "serial": "outu8",
        "hash_crop": {"x": 0, "y": 24, "w": 640, "h": 456},
    },
    "zealos": {
        "id": "zealos",
        "name": "ZealOS Public Domain BIOS (2025-11-10)",
        "default": False,
        "iso_filename": "ZealOS-PublicDomain-BIOS-2025-11-10-02_56_42.iso",
        "url": "https://github.com/Zeal-Operating-System/ZealOS/releases/download/latest/ZealOS-PublicDomain-BIOS-2025-11-10-02_56_42.iso",
        "sha256": "a9c283d79af5938f053cc342666fdea8eeaeb2a2675f3e868aae0cbfad1d1bf0",
        "md5": "63aa076abad9fdec4da609318b1ec0e6",
        "bytes": 43_880_448,
        "commit": "eee210f4379ba3d00b47507f336a158eefb2c993",
        "width": 1024,
        "height": 768,
        "bus": "ahci",
        "mouse": "relative",
        "serial": "outu8",
        "hash_crop": {"x": 0, "y": 24, "w": 1024, "h": 744},
    },
}


class FlavorError(ValueError):
    def __init__(self, message: str, *, code: str = "unknown_flavor") -> None:
        super().__init__(message)
        self.code = code


def get_flavor(flavor_id: str | None = None) -> dict[str, Any]:
    """Return a copy of the flavor record. Default is TinkerOS."""
    key = (flavor_id or DEFAULT).strip().lower() or DEFAULT
    if key not in FLAVORS:
        raise FlavorError(
            f"Unknown flavor {flavor_id!r}. Use one of: {', '.join(FLAVOR_IDS)}.",
            code="unknown_flavor",
        )
    return dict(FLAVORS[key])


def iso_filename(flavor_id: str | None = None) -> str:
    return str(get_flavor(flavor_id)["iso_filename"])


def guest_size(flavor_id: str | None = None) -> tuple[int, int]:
    rec = get_flavor(flavor_id)
    return int(rec["width"]), int(rec["height"])


def mouse_strategy(flavor_id: str | None = None) -> str:
    return str(get_flavor(flavor_id)["mouse"])


def serial_strategy(flavor_id: str | None = None) -> str:
    return str(get_flavor(flavor_id)["serial"])


def hash_crop(flavor_id: str | None = None) -> dict[str, int]:
    return dict(get_flavor(flavor_id)["hash_crop"])


def machine_args(*, accel: str = "tcg") -> list[str]:
    """Common machine flags. ``accel`` is tcg or kvm (caller must have proven kvm)."""
    if accel not in ("tcg", "kvm"):
        raise FlavorError(f"accel must be tcg or kvm, not {accel!r}", code="invalid_args")
    return [
        "-machine", MACHINE,
        "-accel", accel,
        "-cpu", CPU,
        "-m", MEMORY,
        "-smp", SMP,
        "-vga", VGA,
        "-display", "none",
        "-nic", "none",
    ]


def socket_args(*, qmp: Path, vnc: Path, com1: Path) -> list[str]:
    """Unix-only QMP, VNC and COM1. Never a TCP VNC port."""
    return [
        "-qmp", f"unix:{qmp},server=on,wait=off",
        "-vnc", f"unix:{vnc}",
        "-serial", f"unix:{com1},server=on,wait=off",
    ]


def disk_args(flavor_id: str | None, iso: Path, disk: Path) -> list[str]:
    """Attach the ISO and a writable qcow2 (required for savevm even on a live CD)."""
    rec = get_flavor(flavor_id)
    bus = rec["bus"]
    iso_s = str(iso)
    disk_s = str(disk)
    if bus == "ide":
        return [
            "-cdrom", iso_s,
            "-boot", "order=d,menu=on",
            "-drive", f"file={disk_s},format=qcow2,if=ide,index=1,media=disk",
        ]
    if bus == "ahci":
        # ZealOS live CD reboots on plain IDE; AHCI was required in the bake-off.
        return [
            "-device", "ahci,id=ahci",
            "-drive", f"file={iso_s},if=none,id=cdrom,media=cdrom,readonly=on,format=raw",
            "-device", "ide-cd,drive=cdrom,bus=ahci.0,bootindex=1",
            "-drive", f"file={disk_s},if=none,id=hd,format=qcow2",
            "-device", "ide-hd,drive=hd,bus=ahci.1",
        ]
    raise FlavorError(f"Unsupported disk bus {bus!r}", code="invalid_args")


def assert_airgap(argv: list[str]) -> None:
    """Refuse any argv that would attach a NIC other than -nic none."""
    text = " ".join(argv)
    if "-nic none" not in " ".join(argv):
        raise FlavorError("argv must include -nic none; networking stays off.", code="invalid_args")
    forbidden = ("-netdev", "-nic user", "-nic tap", "-nic bridge", "-nic socket")
    for token in forbidden:
        if token in text:
            raise FlavorError(
                f"argv must not enable networking ({token}). Networking stays off.",
                code="invalid_args",
            )


def summarize() -> list[dict[str, Any]]:
    """Public, secret-free flavor list for status/doctor."""
    rows = []
    for key in FLAVOR_IDS:
        rec = get_flavor(key)
        rows.append(
            {
                "id": rec["id"],
                "name": rec["name"],
                "default": bool(rec["default"]),
                "width": rec["width"],
                "height": rec["height"],
                "bus": rec["bus"],
                "mouse": rec["mouse"],
                "serial": rec["serial"],
                "iso_filename": rec["iso_filename"],
                "sha256": rec["sha256"],
                "url": rec["url"],
            }
        )
    return rows


def as_public(rec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": rec["id"],
        "name": rec["name"],
        "width": rec["width"],
        "height": rec["height"],
        "bus": rec["bus"],
        "mouse": rec["mouse"],
        "serial": rec["serial"],
    }
