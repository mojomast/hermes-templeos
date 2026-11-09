"""QEMU child process and argv builder.

Slice A (feat/vm) implements this module. Use flavors.machine_args, disk_args
and socket_args, envsafe.child_env, and argument arrays with no shell.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence


def build_argv(
    *,
    flavor: str,
    iso: Path,
    disk: Path,
    qmp: Path,
    vnc: Path,
    com1: Path,
    accel: str = "tcg",
    name: str = "templeos",
) -> list[str]:
    """Build the qemu-system-x86_64 argv (no shell). Must include -nic none.

    Attach a writable qcow2 even in live-CD mode so savevm has a target.
    Do not add usb-tablet or virtio input. Do not enable networking.
    """
    raise NotImplementedError("templeos.qemu.build_argv: Slice A (feat/vm)")


def spawn(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path | None = None,
    log_path: Path | None = None,
) -> subprocess.Popen[bytes]:
    """Start QEMU with an explicit env allowlist. Never omit env=."""
    raise NotImplementedError("templeos.qemu.spawn: Slice A (feat/vm)")


def terminate(proc: subprocess.Popen[Any] | None, *, timeout_s: float = 5.0) -> None:
    """Politely stop the child, then kill if it ignores the wait."""
    raise NotImplementedError("templeos.qemu.terminate: Slice A (feat/vm)")


def is_running(proc: subprocess.Popen[Any] | None) -> bool:
    """True when the child is still alive."""
    raise NotImplementedError("templeos.qemu.is_running: Slice A (feat/vm)")
