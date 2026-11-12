"""VM lifecycle: start, stop, reset, snapshot, restore, status.

Pitfalls proven in the bake-off:
  * Eject a writable raw floppy (and any non-qcow2 writable device) before savevm.
  * After a failed loadvm the VM is paused in restore-vm; always send cont.
  * Open COM1 before the guest writes, or bytes are lost.
  * Attach a writable qcow2 even in live-CD mode so savevm has a target.
  * Use kvm only after doctor opens /dev/kvm successfully, else tcg.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from templeos import diskimage
from templeos import doctor as doctor_mod
from templeos.envsafe import child_env
from templeos.flavors import DEFAULT, DISK_SIZE, FlavorError, get_flavor
from templeos.settings import load_preferred
from templeos.paths import disks_dir, ensure_layout, home, isos_dir, socket_paths
from templeos.qemu import (
    build_argv,
    create_disk,
    find_binary,
    is_running as qemu_is_running,
    list_snapshots,
    spawn,
    terminate,
)
from templeos.qmp import QMPClient, QMPError
from templeos.serial import SerialPort

GOLDEN = "golden"
PID_NAME = "qemu.pid"
STATE_NAME = "vm-state.json"
LOG_NAME = "qemu.log"
_SNAPSHOT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_LOCK = threading.RLock()

# Test seams (monkeypatch these; they are not a stable public API).
qmp_factory: Callable[[], Any] = QMPClient
serial_factory: Callable[[], Any] = SerialPort


@dataclass
class Runtime:
    proc: Any
    qmp: Any
    serial: Any
    flavor: str
    accel: str
    snapshot: str | None
    pid: int | None
    home: Path
    iso: Path
    disk: Path
    sockets: dict[str, Path] = field(default_factory=dict)
    boot_from_disk: bool = False


_runtime: Runtime | None = None


def start(*, flavor: str | None = None, snapshot: str = GOLDEN, skip_prompts: bool = True) -> dict[str, Any]:
    """Boot the guest. Prefer loadvm of ``snapshot`` when it exists, else the ISO.

    When ``skip_prompts`` is true (default) and the guest boots from the ISO
    instead of a snapshot, a background helper dismisses the first-boot
    "Install onto hard drive (y or n)?" and "Take Tour" prompts by sending Esc
    (to clear AutoComplete focus) then ``n`` + Enter via the existing input
    path. No new tool is required.

    If QEMU is already running in this state directory (including an orphan
    left after a gateway restart), reconnect QMP/COM1 and bind screen/input
    instead of failing with vm_already_running.

    Returns a status dict: running, flavor, accel, snapshot, pid (never tokens
    or socket contents; socket paths only as existence flags). A successful
    reconnect sets attached=True.
    """
    with _LOCK:
        return _start(flavor=flavor, snapshot=snapshot, skip_prompts=skip_prompts)


def stop() -> dict[str, Any]:
    """Stop the QEMU child and close QMP/serial."""
    with _LOCK:
        return _stop()


def reset() -> dict[str, Any]:
    """Reset the running guest (QMP system_reset), or equivalent."""
    with _LOCK:
        rt = _require_running()
        if not isinstance(rt, Runtime):
            return rt
        try:
            rt.qmp.cmd("system_reset")
        except Exception as exc:
            return _fail("The guest reset failed.", "internal_error", str(exc))
        return status()


def snapshot(name: str = GOLDEN) -> dict[str, Any]:
    """savevm ``name``. Eject non-qcow2 writables first."""
    with _LOCK:
        return _snapshot(name)


def restore(name: str = GOLDEN) -> dict[str, Any]:
    """loadvm ``name``. If the VM is left paused (including a failed loadvm), cont."""
    with _LOCK:
        return _restore(name)


def status() -> dict[str, Any]:
    """Current VM state. Socket paths are existence flags only; never tokens."""
    with _LOCK:
        return _status()


def current() -> Runtime | None:
    """The in-process runtime, if a VM was started in this process."""
    return _runtime


def get_runtime() -> Runtime | None:
    """In-process runtime for screen/input binding (None if the VM is stopped)."""
    return _runtime


def get_serial() -> Any | None:
    """Open COM1 port for the current session, or None if it is not connected."""
    rt = _runtime
    if rt is None:
        return None
    serial = rt.serial
    if serial is not None and getattr(serial, "connected", False):
        return serial
    return None


def available_snapshots() -> dict[str, Any]:
    """Named savevm snapshots on the current (or default flavor) disk."""
    with _LOCK:
        root = home()
        rt = _runtime
        disk = rt.disk if rt is not None else None
        current = rt.snapshot if rt is not None else None
        if disk is None:
            state = _read_state(root)
            flavor = str(state.get("flavor") or load_preferred())
            try:
                rec = get_flavor(flavor)
                disk = disks_dir(root) / f"{rec['id']}.qcow2"
            except Exception:
                disk = None
            current = state.get("snapshot")
        names: list[str] = []
        if disk is not None:
            try:
                names = list(list_snapshots(disk))
            except Exception:
                names = []
        return {"ok": True, "snapshots": names, "snapshot": current}


def _start(*, flavor: str | None, snapshot: str, skip_prompts: bool = True) -> dict[str, Any]:
    flavor = flavor or load_preferred()
    try:
        rec = get_flavor(flavor)
    except FlavorError as exc:
        return _fail(str(exc), getattr(exc, "code", "unknown_flavor"))
    snap_name = _check_snapshot_name(snapshot)
    if isinstance(snap_name, dict):
        return snap_name

    root = ensure_layout()
    alive = _cleanup_stale(root)
    if alive or _process_is_up():
        attached = _attach_existing(root)
        if attached.get("ok"):
            return attached
        return _fail(
            str(attached.get("error") or "A TempleOS VM is already running in this state directory."),
            str(attached.get("code") or "vm_already_running"),
            str(attached.get("fix") or "Call templeos_vm op=status, or stop first."),
        )

    qemu = doctor_mod.qemu_version()
    if not qemu.get("ok"):
        return _fail(
            str(qemu.get("error") or "qemu-system-x86_64 was not found on PATH."),
            "qemu_missing",
            str(qemu.get("fix") or "Install qemu-system-x86_64 and qemu-img with your package manager."),
        )

    plan = diskimage.boot_plan(rec["id"])
    boot_from_disk = plan.get("mode") == "disk"
    if boot_from_disk:
        # The verified base image stays untouched; boot a per-user overlay.
        iso = isos_dir(root) / str(rec["iso_filename"])
        disk = Path(str(plan["overlay"]))
        try:
            diskimage.ensure_overlay(Path(str(plan["base"])), disk)
        except Exception as exc:
            return _fail(
                f"Could not create the preinstalled-disk overlay: {exc}",
                "disk_image_overlay_failed",
                "Check qemu-img, or set disk_image off to boot the live ISO.",
            )
    else:
        iso_info = doctor_mod.ensure_iso(rec["id"], fetch=False)
        if not iso_info.get("ok"):
            return _fail(
                str(iso_info.get("error") or "Pinned ISO is not in the cache."),
                str(iso_info.get("code") or "iso_missing"),
                str(iso_info.get("fix") or "Run templeos_vm op=doctor to fetch and pin the official ISO."),
            )
        iso = Path(iso_info["path"])
        disk = disks_dir(root) / f"{rec['id']}.qcow2"
        try:
            create_disk(disk, DISK_SIZE)
        except Exception as exc:
            return _fail(
                f"Could not create the qcow2 disk: {exc}",
                "qemu_missing",
                "Install qemu-img (qemu-utils) and retry start.",
            )

    socks = socket_paths(root)
    for path in socks.values():
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    accel = "kvm" if doctor_mod.kvm_usable() else "tcg"
    vm_name = f"templeos-{rec['id']}"
    argv = build_argv(
        flavor=rec["id"],
        iso=iso,
        disk=disk,
        qmp=socks["qmp"],
        vnc=socks["vnc"],
        com1=socks["com1"],
        accel=accel,
        name=vm_name,
        boot_from_disk=boot_from_disk,
    )
    log_path = root / LOG_NAME
    try:
        proc = spawn(argv, env=child_env(), cwd=root, log_path=log_path)
    except FileNotFoundError:
        return _fail(
            "qemu-system-x86_64 was not found on PATH.",
            "qemu_missing",
            "Install qemu-system-x86_64 with your package manager.",
        )
    except Exception as exc:
        return _fail(f"Failed to spawn QEMU: {exc}", "doctor_failed")

    exit_code = proc.poll()
    if exit_code is not None:
        _clear_pidfile(root)
        tail = _qemu_log_tail(root)
        detail = f"QEMU exited immediately (code {exit_code})."
        if tail:
            detail += " QEMU said: " + tail
        return _fail(
            detail,
            "qemu_start_failed",
            "Check for a qemu-system-x86_64 wrapper that appends another -drive ...index=0; run templeos_vm op=doctor.",
        )

    _write_pidfile(root, proc.pid)
    qmp = qmp_factory()
    serial = serial_factory()
    try:
        qmp.connect(socks["qmp"])
        # Open COM1 immediately and keep it open for the session.
        serial.open(socks["com1"])
    except Exception as exc:
        terminate(proc, timeout_s=3.0)
        _clear_pidfile(root)
        _close_quietly(qmp, serial)
        tail = _qemu_log_tail(root) if proc.poll() is not None else ""
        detail = f"QEMU started but QMP or COM1 could not be opened: {exc}"
        if tail:
            detail += " QEMU said: " + tail
        return _fail(
            detail,
            "doctor_failed",
            "Check templeos_vm op=doctor; a qemu wrapper that adds another index=0 drive can make QEMU exit immediately.",
        )

    global _runtime
    _runtime = Runtime(
        proc=proc,
        qmp=qmp,
        serial=serial,
        flavor=rec["id"],
        accel=accel,
        snapshot=None,
        pid=proc.pid,
        home=root,
        iso=iso,
        disk=disk,
        sockets=socks,
        boot_from_disk=boot_from_disk,
    )
    _write_state(root, _runtime)
    _bind_screen(_runtime)

    wanted = snap_name
    restored = False
    if wanted and wanted in list_snapshots(disk):
        loaded = _restore(wanted)
        if not loaded.get("ok", True) and loaded.get("code"):
            # ISO boot continues; surface that the named snapshot was not applied
            # by leaving snapshot=None. The VM itself is still running.
            pass
        else:
            _runtime.snapshot = wanted
            _write_state(root, _runtime)
            restored = True

    try:
        from templeos.frame_cache import get_frame_cache

        get_frame_cache().poke()
    except Exception:
        pass

    # First-boot ISO prompts steal focus into AutoComplete unless Esc'd first.
    if skip_prompts and not restored and not boot_from_disk:
        _schedule_first_boot_dismiss()

    return _status()


def _stop() -> dict[str, Any]:
    global _runtime
    root = home()
    rt = _runtime
    proc = rt.proc if rt is not None else None
    qmp = rt.qmp if rt is not None else None
    serial = rt.serial if rt is not None else None
    pid = _read_pidfile(root)
    if qmp is not None:
        try:
            qmp.cmd("quit", timeout_s=2.0)
        except TypeError:
            try:
                qmp.cmd("quit")
            except Exception:
                pass
        except Exception:
            pass
    _close_quietly(qmp, serial)
    if proc is not None:
        terminate(proc, timeout_s=4.0)
    elif pid is not None and _pid_is_qemu(pid):
        _kill_pid(pid)
    _clear_pidfile(root)
    try:
        for path in socket_paths(root).values():
            path.unlink(missing_ok=True)
    except OSError:
        pass
    flavor = rt.flavor if rt is not None else load_preferred()
    _runtime = None
    _unbind_screen()
    try:
        from templeos.frame_cache import get_frame_cache

        get_frame_cache().reset()
    except Exception:
        pass
    state_path = root / STATE_NAME
    if state_path.exists():
        try:
            payload = json.loads(state_path.read_text() or "{}")
        except ValueError:
            payload = {}
        payload["running"] = False
        payload["pid"] = None
        try:
            state_path.write_text(json.dumps(payload, indent=2) + "\n")
        except OSError:
            pass
    return {
        "ok": True,
        "running": False,
        "flavor": flavor,
        "accel": None,
        "snapshot": None,
        "pid": None,
        "kvm": doctor_mod.kvm_usable(),
        "sockets": _socket_flags(root),
    }


def _snapshot(name: str) -> dict[str, Any]:
    rt = _require_running()
    if not isinstance(rt, Runtime):
        return rt
    checked = _check_snapshot_name(name)
    if isinstance(checked, dict):
        return checked
    _eject_non_qcow2_writables(rt.qmp)
    try:
        rt.qmp.hmp(f"savevm {checked}")
    except Exception as exc:
        return _fail(
            f"savevm {checked} failed: {exc}",
            "snapshot_failed",
            "Eject non-qcow2 writables and retry snapshot.",
        )
    rt.snapshot = checked
    _write_state(rt.home, rt)
    body = _status()
    body["name"] = checked
    return body


def _restore(name: str) -> dict[str, Any]:
    rt = _require_running()
    if not isinstance(rt, Runtime):
        return rt
    checked = _check_snapshot_name(name)
    if isinstance(checked, dict):
        return checked
    failed: Exception | None = None
    try:
        rt.qmp.hmp(f"loadvm {checked}")
    except Exception as exc:
        failed = exc
    # Always send cont: loadvm leaves the VM paused on success, and a failed
    # loadvm stays in restore-vm until cont.
    _cont(rt.qmp)
    if failed is not None:
        return _fail(
            f"loadvm {checked} failed: {failed}",
            "restore_failed",
            "The plugin must send cont if loadvm left the VM paused, then retry.",
        )
    rt.snapshot = checked
    _write_state(rt.home, rt)
    body = _status()
    body["name"] = checked
    return body


def _attach_existing(root: Path) -> dict[str, Any]:
    """Reconnect QMP/COM1 to a live QEMU (same process, or after a gateway restart)."""
    global _runtime
    if _runtime is not None and _process_is_up():
        return _status()
    if _runtime is not None:
        _close_quietly(_runtime.qmp, _runtime.serial)
        _runtime = None
        _unbind_screen()

    pid = _read_pidfile(root)
    if not (pid and _pid_is_qemu(pid)):
        return _fail(
            "The TempleOS VM is not running.",
            "vm_not_running",
            "Call templeos_vm op=start, then retry.",
        )

    socks = socket_paths(root)
    if not socks["qmp"].exists():
        return _fail(
            "QEMU is running but the QMP socket is missing.",
            "doctor_failed",
            "Call templeos_vm op=stop, then start again.",
        )

    state = _read_state(root) or {}
    flavor = str(state.get("flavor") or load_preferred())
    try:
        rec = get_flavor(flavor)
        flavor_id = rec["id"]
        iso_name = str(state.get("iso") or rec["iso_filename"])
        default_disk = disks_dir(root) / f"{rec['id']}.qcow2"
    except FlavorError as exc:
        return _fail(str(exc), getattr(exc, "code", "unknown_flavor"))

    iso = isos_dir(root) / iso_name
    disk_s = state.get("disk")
    disk = Path(disk_s) if disk_s else default_disk
    accel = str(state.get("accel") or ("kvm" if doctor_mod.kvm_usable() else "tcg"))
    snapshot = state.get("snapshot")
    boot_from_disk = bool(state.get("disk_image"))

    qmp = qmp_factory()
    serial = serial_factory()
    try:
        qmp.connect(socks["qmp"])
        if socks["com1"].exists():
            serial.open(socks["com1"])
    except Exception as exc:
        _close_quietly(qmp, serial)
        return _fail(
            f"QEMU is running but QMP or COM1 could not be reattached: {exc}",
            "doctor_failed",
            "Call templeos_vm op=stop, then start again.",
        )

    _runtime = Runtime(
        proc=None,
        qmp=qmp,
        serial=serial,
        flavor=flavor_id,
        accel=accel,
        snapshot=snapshot if isinstance(snapshot, str) or snapshot is None else str(snapshot),
        pid=pid,
        home=root,
        iso=iso,
        disk=disk,
        sockets=socks,
        boot_from_disk=boot_from_disk,
    )
    _write_state(root, _runtime)
    _bind_screen(_runtime)
    try:
        from templeos.frame_cache import get_frame_cache

        get_frame_cache().poke()
    except Exception:
        pass
    body = _status()
    body["attached"] = True
    return body


def _status() -> dict[str, Any]:
    root = home()
    rt = _runtime
    running = _process_is_up()
    socks = _socket_flags(root)
    if rt is not None and running:
        return {
            "ok": True,
            "running": True,
            "flavor": rt.flavor,
            "accel": rt.accel,
            "snapshot": rt.snapshot,
            "pid": rt.pid,
            "kvm": doctor_mod.kvm_usable(),
            "sockets": socks,
        }
    # Fall back to the on-disk state when this process has no runtime
    # (for example after a crash) but still report running truthfully.
    flavor = load_preferred()
    accel = None
    snapshot = None
    pid = _read_pidfile(root)
    state = _read_state(root)
    if state:
        flavor = str(state.get("flavor") or flavor)
        accel = state.get("accel")
        snapshot = state.get("snapshot")
    live = bool(pid and _pid_is_qemu(pid))
    return {
        "ok": True,
        "running": live,
        "flavor": flavor,
        "accel": accel if live else None,
        "snapshot": snapshot if live else None,
        "pid": pid if live else None,
        "kvm": doctor_mod.kvm_usable(),
        "sockets": socks,
    }


def _process_is_up() -> bool:
    rt = _runtime
    if rt is None:
        pid = _read_pidfile(home())
        return bool(pid and _pid_is_qemu(pid))
    if qemu_is_running(rt.proc):
        return True
    pid = rt.pid
    return bool(pid and _pid_is_qemu(pid))


def _require_running() -> Runtime | dict[str, Any]:
    if _runtime is not None and _process_is_up():
        return _runtime
    root = home()
    if _cleanup_stale(root) or _process_is_up():
        attached = _attach_existing(root)
        if attached.get("ok") and _runtime is not None:
            return _runtime
    return _fail(
        "The TempleOS VM is not running.",
        "vm_not_running",
        "Call templeos_vm op=start, then retry.",
    )


def _eject_non_qcow2_writables(qmp: Any) -> None:
    devices: list[dict[str, Any]] = []
    try:
        reply = qmp.cmd("query-block")
        raw = reply.get("return") if isinstance(reply, dict) else None
        if isinstance(raw, list):
            devices = [item for item in raw if isinstance(item, dict)]
    except Exception:
        devices = []
    for dev in devices:
        inserted = dev.get("inserted") or {}
        if not isinstance(inserted, dict) or not inserted:
            continue
        fmt = str(inserted.get("drv") or inserted.get("format") or "").lower()
        read_only = bool(inserted.get("read-only"))
        if read_only or fmt == "qcow2":
            continue
        name = dev.get("device") or dev.get("qdev")
        if not name:
            continue
        try:
            qmp.hmp(f"eject -f {name}")
        except Exception:
            try:
                qmp.cmd("eject", device=str(name), force=True)
            except Exception:
                pass
    # Always try floppy0: a writable raw floppy makes savevm fail, and a
    # missing device is a harmless HMP error.
    try:
        qmp.hmp("eject -f floppy0")
    except Exception:
        pass
    try:
        qmp.hmp("eject floppy0")
    except Exception:
        pass


def _cont(qmp: Any) -> None:
    # Prefer HMP: FakeQMP and the bake-off track paused state through hmp("cont").
    # Fall back to the QMP cont command if HMP is unavailable.
    try:
        qmp.hmp("cont")
        return
    except Exception:
        pass
    try:
        qmp.cmd("cont")
    except Exception:
        pass


def _cleanup_stale(root: Path) -> bool:
    """Return True if a live QEMU owned by this state dir was found."""
    pid = _read_pidfile(root)
    if pid is None:
        return False
    if _pid_is_qemu(pid):
        return True
    # Stale or reused pid: do not kill a non-QEMU process. Drop the pidfile
    # and leftover sockets so a new VM can start.
    _clear_pidfile(root)
    for path in socket_paths(root).values():
        try:
            path.unlink()
        except OSError:
            pass
    return False


def _write_pidfile(root: Path, pid: int) -> None:
    path = root / PID_NAME
    path.write_text(f"{int(pid)}\n")


def _clear_pidfile(root: Path) -> None:
    (root / PID_NAME).unlink(missing_ok=True)


def _read_pidfile(root: Path) -> int | None:
    path = root / PID_NAME
    if not path.is_file():
        return None
    try:
        text = path.read_text().strip().splitlines()[0]
    except OSError:
        return None
    if not text.isdigit():
        return None
    return int(text)


def _write_state(root: Path, rt: Runtime) -> None:
    payload = {
        "flavor": rt.flavor,
        "accel": rt.accel,
        "snapshot": rt.snapshot,
        "pid": rt.pid,
        "running": True,
        "disk": str(rt.disk),
        "iso": str(rt.iso.name),
        "disk_image": bool(rt.boot_from_disk),
    }
    try:
        (root / STATE_NAME).write_text(json.dumps(payload, indent=2) + "\n")
    except OSError:
        pass


def _read_state(root: Path) -> dict[str, Any]:
    path = root / STATE_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text() or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _pid_is_qemu(pid: int) -> bool:
    if not _pid_alive(pid):
        return False
    cmdline = Path(f"/proc/{pid}/cmdline")
    try:
        parts = cmdline.read_bytes().split(b"\0")
    except OSError:
        # /proc may be missing (non-Linux). If the pid is alive, be conservative
        # and treat an existing pidfile as ours only when the in-process runtime
        # matches.
        return _runtime is not None and _runtime.pid == pid
    return any(b"qemu-system-x86_64" in part for part in parts)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _kill_pid(pid: int, *, timeout_s: float = 4.0) -> None:
    try:
        os.kill(pid, 15)
    except OSError:
        return
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, 9)
    except OSError:
        return


def _socket_flags(root: Path) -> dict[str, bool]:
    return {key: path.exists() for key, path in socket_paths(root).items()}


def _close_quietly(qmp: Any, serial: Any) -> None:
    if qmp is not None:
        try:
            qmp.close()
        except Exception:
            pass
    if serial is not None:
        try:
            serial.close()
        except Exception:
            pass


def _check_snapshot_name(name: str) -> str | dict[str, Any]:
    if not isinstance(name, str) or not name.strip():
        return _fail("name must be a simple snapshot id (default golden).", "invalid_args")
    token = name.strip()
    if "/" in token or "\\" in token or ".." in token or not _SNAPSHOT_NAME.match(token):
        return _fail("name must be a simple snapshot id (default golden).", "invalid_args")
    return token


def _bind_screen(rt: Runtime) -> None:
    """Attach the live QMP/serial session so screen and input can use it."""
    try:
        from templeos.screen import bind as bind_screen
    except Exception:
        return
    try:
        bind_screen(qmp=rt.qmp, serial=rt.serial, flavor=rt.flavor, state_dir=rt.home)
    except Exception:
        return


def _unbind_screen() -> None:
    try:
        from templeos.screen import unbind as unbind_screen
    except Exception:
        return
    try:
        unbind_screen()
    except Exception:
        return


def _qemu_log_tail(root: Path, limit: int = 1600) -> str:
    """Short, sanitized tail of qemu.log for start errors (no home paths)."""

    try:
        data = (root / LOG_NAME).read_bytes()[-limit:]
    except OSError:
        return ""
    text = data.decode("utf-8", "replace").strip()
    if not text:
        return ""
    text = text.replace(str(root), "<data>")
    text = text.replace(str(Path.home()), "<home>")
    text = re.sub(r"/(?:home|workspace|Users)/[^\s:'\"]+", "<path>", text)
    text = re.sub(r"[A-Za-z]:\\Users\\[^\s]+", "<path>", text)
    return text[-limit:]


def _fail(error: str, code: str, fix: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": error,
        "code": code,
        "fix": fix or "See docs/CONTRACTS.md.",
        "running": _process_is_up(),
    }


_FIRST_BOOT_THREAD: threading.Thread | None = None
_FIRST_BOOT_LOCK = threading.Lock()


def _schedule_first_boot_dismiss() -> None:
    """Background: dismiss Install/Tour prompts without blocking start()."""
    global _FIRST_BOOT_THREAD
    with _FIRST_BOOT_LOCK:
        if _FIRST_BOOT_THREAD is not None and _FIRST_BOOT_THREAD.is_alive():
            return
        _FIRST_BOOT_THREAD = threading.Thread(
            target=_dismiss_first_boot_prompts,
            name="templeos-first-boot",
            daemon=True,
        )
        _FIRST_BOOT_THREAD.start()


def _dismiss_first_boot_prompts(*, timeout_s: float = 120.0) -> dict[str, Any]:
    """Answer first-boot y/n prompts via the existing input path.

    TinkerOS/TempleOS show "Install onto hard drive (y or n)?" then
    "Take Tour (y or n)?". AutoComplete often holds keyboard focus, so we
    send Esc first, then ``n`` + Enter for each prompt. Runs off the start()
    request path so the gateway stays responsive.
    """
    deadline = time.monotonic() + float(timeout_s)
    answered = 0
    last_text = ""
    while time.monotonic() < deadline and answered < 2:
        if _runtime is None:
            return {"ok": False, "answered": answered, "reason": "vm_stopped"}
        try:
            from templeos import input as inp
            from templeos.screen import read_text, wait_idle
        except Exception as exc:
            return {"ok": False, "answered": answered, "error": str(exc)}
        try:
            wait_idle(timeout_s=2.0, stable_ms=150)
        except Exception:
            pass
        try:
            body = read_text()
        except Exception:
            body = {}
        text = str((body or {}).get("text") or "")
        last_text = text
        lower = text.lower()
        needs_install = "install onto hard drive" in lower and "y or n" in lower
        needs_tour = "take tour" in lower and "y or n" in lower
        if not needs_install and not needs_tour:
            # Already past prompts (or snapshot).
            if "t:/home>" in lower or "home>" in lower:
                return {"ok": True, "answered": answered, "skipped": True}
            time.sleep(1.0)
            continue
        try:
            # Esc clears AutoComplete / focus so ``n`` lands on the y/n prompt.
            inp.send_keys(["esc"], hold_ms=40)
            time.sleep(0.15)
            inp.type_text("n", delay_s=0.0)
            time.sleep(0.05)
            inp.send_keys(["ret"], hold_ms=40)
            answered += 1
            time.sleep(0.8)
        except Exception as exc:
            return {"ok": False, "answered": answered, "error": str(exc), "text": last_text[:200]}
    return {"ok": answered > 0, "answered": answered, "text": last_text[:200]}
