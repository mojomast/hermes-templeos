"""Host <-> guest file transfer.

Slice D (feat/files-docs) implements this module.

Not proven end-to-end in the bake-off. Candidates: TinkerOS TOSClient,
a stopped-VM FAT32 second disk, or a serial file protocol. Never mount
the live RedSea qcow2 while QEMU has it open. Host paths must be confined
under the plugin data dir (tools.py already confines dest/src).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def list_guest(path: str = "T:/") -> dict[str, Any]:
    """List a guest path. Returns names, dirs, and errors in the envelope fields."""
    raise NotImplementedError("templeos.files.list_guest: Slice D (feat/files-docs)")


def pull(guest_path: str, host_dest: Path) -> dict[str, Any]:
    """Copy a guest file into a confined host path."""
    raise NotImplementedError("templeos.files.pull: Slice D (feat/files-docs)")


def push(host_src: Path, guest_path: str) -> dict[str, Any]:
    """Copy a confined host file into the guest."""
    raise NotImplementedError("templeos.files.push: Slice D (feat/files-docs)")
