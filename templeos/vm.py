"""VM lifecycle: start, stop, reset, snapshot, restore, status.

Slice A (feat/vm) implements this module.

Pitfalls proven in the bake-off:
  * Eject a writable raw floppy (and any non-qcow2 writable device) before savevm.
  * After a failed loadvm the VM is paused in restore-vm; always send cont.
  * Open COM1 before the guest writes, or bytes are lost.
  * Attach a writable qcow2 even in live-CD mode so savevm has a target.
  * Use kvm only after doctor opens /dev/kvm successfully, else tcg.
"""

from __future__ import annotations

from typing import Any

GOLDEN = "golden"


def start(*, flavor: str = "tinkeros", snapshot: str = GOLDEN) -> dict[str, Any]:
    """Boot the guest. Prefer loadvm of ``snapshot`` when it exists, else the ISO.

    Returns a status dict: running, flavor, accel, snapshot, pid (never tokens
    or socket contents; socket paths only as existence flags).
    """
    raise NotImplementedError("templeos.vm.start: Slice A (feat/vm)")


def stop() -> dict[str, Any]:
    """Stop the QEMU child and close QMP/serial."""
    raise NotImplementedError("templeos.vm.stop: Slice A (feat/vm)")


def reset() -> dict[str, Any]:
    """Reset the running guest (QMP system_reset), or equivalent."""
    raise NotImplementedError("templeos.vm.reset: Slice A (feat/vm)")


def snapshot(name: str = GOLDEN) -> dict[str, Any]:
    """savevm ``name``. Eject non-qcow2 writables first."""
    raise NotImplementedError("templeos.vm.snapshot: Slice A (feat/vm)")


def restore(name: str = GOLDEN) -> dict[str, Any]:
    """loadvm ``name``. If the VM is left paused (including a failed loadvm), cont."""
    raise NotImplementedError("templeos.vm.restore: Slice A (feat/vm)")


def status() -> dict[str, Any]:
    """Current VM state. Socket paths are existence flags only; never tokens."""
    raise NotImplementedError("templeos.vm.status: Slice A (feat/vm)")
