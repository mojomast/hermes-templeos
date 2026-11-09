"""Host doctor: QEMU binary, KVM usability, pinned ISOs, disk, sockets.

Slice A (feat/vm) implements this module.

kvm is usable only when /dev/kvm can actually be opened, not merely when
the node exists. Do not install packages or write udev rules; tell the user
the apt or brew command. Fetch ISOs only from official URLs in flavors.py
and verify the pinned SHA-256 (delete partials on mismatch).
"""

from __future__ import annotations

from typing import Any


def kvm_usable() -> bool:
    """True only if /dev/kvm can be opened read/write. Existence is not enough."""
    raise NotImplementedError("templeos.doctor.kvm_usable: Slice A (feat/vm)")


def qemu_version() -> dict[str, Any]:
    """Locate qemu-system-x86_64 on PATH and return {path, version}."""
    raise NotImplementedError("templeos.doctor.qemu_version: Slice A (feat/vm)")


def ensure_iso(flavor: str = "tinkeros") -> dict[str, Any]:
    """Fetch the pinned ISO if missing, verify SHA-256, refuse a hash mismatch."""
    raise NotImplementedError("templeos.doctor.ensure_iso: Slice A (feat/vm)")


def doctor() -> dict[str, Any]:
    """Full doctor report: qemu, kvm, iso, disk, sockets (existence only), ok, checks."""
    raise NotImplementedError("templeos.doctor.doctor: Slice A (feat/vm)")
