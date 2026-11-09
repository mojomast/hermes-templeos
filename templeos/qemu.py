"""QEMU child process and argv builder.

Use flavors.machine_args, disk_args and socket_args, envsafe.child_env, and
argument arrays with no shell. Network is always off (-nic none). Attach a
writable qcow2 even in live-CD mode so savevm has a target. Do not add
usb-tablet or virtio input.
"""

from __future__ import annotations

import os
import signal
import subprocess
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from templeos.envsafe import CHILD_ENV_ALLOWLIST, child_env
from templeos.flavors import (
    DISK_SIZE,
    QEMU_BINARY,
    QEMU_IMG,
    assert_airgap,
    disk_args,
    machine_args,
    socket_args,
)

# Env names that must never reach a child, even if they somehow appear.
_BLOCKED = frozenset(
    {
        "NODE_OPTIONS",
        "PYTHONHOME",
        "PYTHONPATH",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
    }
)


def find_binary(name: str = QEMU_BINARY) -> Path | None:
    """Return the resolved executable path, or None if it is not on PATH."""
    found = shutil.which(name)
    return Path(found) if found else None


def sanitize_env(env: Mapping[str, str]) -> dict[str, str]:
    """Keep only the child-env allowlist. Never inherit os.environ as-is."""
    safe = {k: v for k, v in env.items() if k in CHILD_ENV_ALLOWLIST and k not in _BLOCKED and v}
    # Fill defaults the allowlist requires so QEMU always has PATH/LANG.
    filled = child_env()
    for key in ("PATH", "LANG", "LC_ALL"):
        safe.setdefault(key, filled[key])
    for blocked in _BLOCKED:
        safe.pop(blocked, None)
    return safe


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
    binary = find_binary(QEMU_BINARY)
    exe = str(binary) if binary is not None else QEMU_BINARY
    safe_name = _safe_name(name)
    argv = [
        exe,
        "-name",
        safe_name,
        *machine_args(accel=accel),
        *socket_args(qmp=Path(qmp), vnc=Path(vnc), com1=Path(com1)),
        *disk_args(flavor, Path(iso), Path(disk)),
    ]
    assert_airgap(argv)
    return argv


def spawn(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path | None = None,
    log_path: Path | None = None,
) -> subprocess.Popen[bytes]:
    """Start QEMU with an explicit env allowlist. Never omit env=."""
    if env is None:
        raise ValueError("spawn requires an explicit env allowlist; never inherit os.environ")
    safe = sanitize_env(env)
    logf = None
    stdout: Any = subprocess.DEVNULL
    stderr: Any = subprocess.DEVNULL
    if log_path is not None:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        logf = path.open("ab")
        stdout = logf
        stderr = logf
    try:
        proc: subprocess.Popen[bytes] = subprocess.Popen(
            list(argv),
            env=safe,
            cwd=str(cwd) if cwd is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        if logf is not None:
            logf.close()
        raise
    # The child holds a dup of the log fd; the Python handle can close.
    if logf is not None:
        logf.close()
    return proc


def terminate(proc: subprocess.Popen[Any] | None, *, timeout_s: float = 5.0) -> None:
    """Politely stop the child, then kill if it ignores the wait."""
    if proc is None or not is_running(proc):
        return
    pid = proc.pid
    _signal_group(pid, signal.SIGTERM)
    try:
        proc.wait(timeout=timeout_s)
        return
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        pass
    _signal_group(pid, signal.SIGKILL)
    try:
        proc.wait(timeout=2.0)
    except (subprocess.TimeoutExpired, OSError):
        # Last resort: signal the process itself if the group wait failed.
        try:
            proc.kill()
            proc.wait(timeout=1.0)
        except (subprocess.TimeoutExpired, OSError):
            return


def is_running(proc: subprocess.Popen[Any] | None) -> bool:
    """True when the child is still alive."""
    if proc is None:
        return False
    return proc.poll() is None


def create_disk(path: Path, size: str = DISK_SIZE) -> Path:
    """Create a qcow2 at ``path`` if it does not already exist."""
    dest = Path(path)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    binary = find_binary(QEMU_IMG)
    exe = str(binary) if binary is not None else QEMU_IMG
    argv = [exe, "create", "-f", "qcow2", str(dest), size]
    completed = subprocess.run(
        argv,
        env=child_env(),
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0 or not dest.exists():
        if dest.exists():
            dest.unlink()
        detail = (completed.stderr or completed.stdout or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(detail or f"{QEMU_IMG} create failed for {dest}")
    return dest


def list_snapshots(disk: Path) -> list[str]:
    """Return snapshot tags stored on a qcow2, or an empty list."""
    path = Path(disk)
    if not path.is_file():
        return []
    binary = find_binary(QEMU_IMG)
    exe = str(binary) if binary is not None else QEMU_IMG
    argv = [exe, "info", "--output=json", str(path)]
    completed = subprocess.run(
        argv,
        env=child_env(),
        capture_output=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        return []
    try:
        import json

        payload = json.loads(completed.stdout.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return []
    names: list[str] = []
    for item in payload.get("snapshots") or []:
        if not isinstance(item, dict):
            continue
        tag = item.get("name") or item.get("tag")
        if tag:
            names.append(str(tag))
    return names


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name.strip())
    return cleaned[:64] or "templeos"


def _signal_group(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
        return
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        return
