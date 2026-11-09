"""Host <-> guest file transfer over COM1, plus an experimental FAT push.

Primary path: a framed, checksummed serial protocol (COM1) driven by the
HolyC helper in ``skills/templeos-operator/guest/Xfer.HC``. The helper is
typed into the guest via ``templeos_input`` ``op=holyc`` (Slice B) after
``CommInit`` / ``CommInit8n1`` on TinkerOS.

Fallback: when the VM is stopped, ``push`` can build a small FAT image
under the exchange dir for the guest to read later. The bake-off found a
hot-added FAT12 floppy was not visible as ``A:`` on the TinkerOS live CD,
so that path is marked ``experimental`` and never mounts a live RedSea
qcow2 while QEMU has it open.

Host paths are confined by ``templeos.tools`` before this module is called.
Guest paths are sanitized here. Size caps apply to both directions.
"""

from __future__ import annotations

import json
import os
import re
import struct
import subprocess
from pathlib import Path
from typing import Any, Protocol

from templeos.envsafe import child_env
from templeos.paths import PathError, confine, ensure_layout, home

# --- constants ----------------------------------------------------------------

MAGIC = b"TXFR"
PROTO_VERSION = 1

CMD_LIST = 0x01
CMD_PULL = 0x02
CMD_PUSH = 0x03
CMD_LIST_OK = 0x81
CMD_PULL_OK = 0x82
CMD_PUSH_OK = 0x83
CMD_ERR = 0x8F

MAX_FILE_BYTES = 256 * 1024
MAX_PATH_CHARS = 200
MAX_LIST_ENTRIES = 512
DEFAULT_TIMEOUT_S = 8.0
EXCHANGE_DIR = "exchange"
FAT_IMAGE_NAME = "xfer.img"
FAT_IMAGE_BYTES = 1_474_560  # 1440 KiB floppy-sized image; experimental

# Guest paths look like T:/Home/Foo.HC or T:/Demo/A.HC. No .., no spaces.
_GUEST_PATH_RE = re.compile(
    r"^[A-Za-z]:(?:/(?:[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*))?/?$"
)
_GUEST_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

HELPER_REL = Path("skills") / "templeos-operator" / "guest" / "Xfer.HC"


class SerialLike(Protocol):
    connected: bool

    def write(self, data: bytes) -> int: ...

    def read(self, n: int = 4096, *, timeout_s: float = 0.2) -> bytes: ...


_bound_serial: SerialLike | None = None


def bind_serial(port: SerialLike | None) -> None:
    """Inject a SerialPort or FakeSerial for the current session / tests."""
    global _bound_serial
    _bound_serial = port


def get_serial() -> SerialLike | None:
    """Return the bound COM1 port, or ask the VM module once Slice A lands."""
    if _bound_serial is not None:
        if getattr(_bound_serial, "connected", False):
            return _bound_serial
        return None
    try:
        from templeos import vm as vm_mod  # Slice A

        getter = getattr(vm_mod, "get_serial", None)
        if callable(getter):
            port = getter()
            if port is not None and getattr(port, "connected", False):
                return port
    except Exception:
        return None
    return None


def helper_source_path() -> Path:
    """Absolute path to the HolyC Xfer helper shipped with the skill."""
    # Repo root is two levels above templeos/ when installed editable;
    # also try next to the installed package's parent (plugin root).
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / HELPER_REL,
        Path.cwd() / HELPER_REL,
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return candidates[0]


def exchange_dir(root: Path | None = None) -> Path:
    """Host exchange directory under the plugin data dir."""
    base = ensure_layout(root) if root is not None else ensure_layout()
    path = base / EXCHANGE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


# --- guest path + name rules --------------------------------------------------

def sanitize_guest_path(path: str, *, allow_dir: bool = True) -> str:
    """Normalize and refuse unsafe guest paths."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("guest path is empty")
    raw = path.strip().replace("\\", "/")
    while "//" in raw:
        raw = raw.replace("//", "/")
    if ".." in raw.split("/"):
        raise ValueError(f"guest path must not contain '..': {path!r}")
    if len(raw) > MAX_PATH_CHARS:
        raise ValueError(f"guest path exceeds {MAX_PATH_CHARS} characters")
    if not _GUEST_PATH_RE.match(raw):
        raise ValueError(
            f"guest path must look like T:/Home/File.HC (got {path!r})"
        )
    if not allow_dir and raw.endswith("/"):
        raise ValueError(f"expected a file path, got directory {path!r}")
    return raw


def sanitize_guest_filename(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("filename is empty")
    name = name.strip()
    if "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError(f"illegal filename: {name!r}")
    if not _GUEST_NAME_RE.match(name):
        raise ValueError(
            f"filename must be [A-Za-z0-9_.-]+ (got {name!r})"
        )
    if len(name) > 64:
        raise ValueError("filename too long")
    return name


# --- framing ------------------------------------------------------------------

def _checksum(cmd: int, payload: bytes) -> int:
    """Additive U32 checksum of cmd + each payload byte (HolyC-friendly)."""
    s = cmd & 0xFF
    for b in payload:
        s = (s + b) & 0xFFFFFFFF
    return s


def encode_frame(cmd: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_FILE_BYTES + MAX_PATH_CHARS + 64:
        raise ValueError("frame payload too large")
    length = len(payload)
    head = MAGIC + struct.pack("<BI", cmd & 0xFF, length)
    csum = _checksum(cmd, payload)
    return head + payload + struct.pack("<I", csum)


def try_decode_frame(buf: bytes) -> tuple[int, bytes, int] | None:
    """Return (cmd, payload, consumed) or None if incomplete / no magic yet."""
    if len(buf) < 9:
        return None
    idx = buf.find(MAGIC)
    if idx < 0:
        return None
    if idx > 0:
        # Caller should discard leading noise; signal by consumed=idx with no frame.
        return -1, b"", idx
    if len(buf) < 9:
        return None
    cmd, length = struct.unpack_from("<BI", buf, 4)
    total = 9 + length + 4
    if len(buf) < total:
        return None
    payload = buf[9 : 9 + length]
    (csum,) = struct.unpack_from("<I", buf, 9 + length)
    if csum != _checksum(cmd, payload):
        raise ValueError("serial frame checksum mismatch")
    return cmd, payload, total


def _read_frame(port: SerialLike, *, timeout_s: float) -> tuple[int, bytes]:
    import time

    deadline = time.monotonic() + max(0.1, timeout_s)
    buf = bytearray()
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        chunk = port.read(4096, timeout_s=min(0.2, remaining))
        if chunk:
            buf.extend(chunk)
            while True:
                decoded = try_decode_frame(bytes(buf))
                if decoded is None:
                    break
                cmd, payload, consumed = decoded
                if cmd == -1:
                    del buf[:consumed]
                    continue
                del buf[:consumed]
                return cmd, payload
        else:
            time.sleep(0.01)
    raise TimeoutError("timed out waiting for a serial file-transfer frame")


def _transact(
    port: SerialLike,
    cmd: int,
    payload: bytes,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> tuple[int, bytes]:
    if not getattr(port, "connected", False):
        raise RuntimeError("serial not open")
    port.write(encode_frame(cmd, payload))
    return _read_frame(port, timeout_s=timeout_s)


def _err_result(message: str, code: str, fix: str | None = None, **fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ok": False,
        "error": message,
        "code": code,
        "fix": fix,
    }
    body.update(fields)
    return body


def _serial_missing() -> dict[str, Any]:
    return _err_result(
        "COM1 is not open. Start the VM and keep the serial reader connected.",
        "serial_not_ready",
        "Call templeos_vm op=start, wait_idle, then initialize Comm* on TinkerOS "
        "(CommInit; CommInit8n1(1,115200);) and load the Xfer.HC helper.",
    )


# --- public API ---------------------------------------------------------------

def list_guest(path: str = "T:/") -> dict[str, Any]:
    """List a guest path over the serial Xfer protocol."""
    try:
        guest = sanitize_guest_path(path, allow_dir=True)
    except ValueError as exc:
        return _err_result(str(exc), "invalid_args", "Use a path like T:/ or T:/Home/.")

    port = get_serial()
    if port is None:
        # Integration stub tests still expect NotImplementedError until feat/integration
        # flips this branch to serial_not_ready (see docs/CONTRACTS.md Files protocol).
        raise NotImplementedError(
            "templeos.files.list_guest: Slice D needs COM1 "
            "(bind_serial in tests, or vm.get_serial once Slice A lands)"
        )

    try:
        cmd, payload = _transact(port, CMD_LIST, guest.encode("utf-8"))
    except TimeoutError as exc:
        return _err_result(str(exc), "timeout", "Raise the timeout or check that Xfer.HC is running.")
    except Exception as exc:
        return _err_result(str(exc), "serial_not_ready", "Re-open COM1 and retry.")

    if cmd == CMD_ERR:
        return _err_result(
            payload.decode("utf-8", errors="replace") or "guest list failed",
            "invalid_args",
            "Check the guest path with Dir; in HolyC.",
        )
    if cmd != CMD_LIST_OK:
        return _err_result(
            f"unexpected serial reply cmd=0x{cmd:02x}",
            "serial_not_ready",
            "Reload Xfer.HC in the guest and retry.",
        )
    try:
        entries = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _err_result("guest list payload was not JSON", "serial_not_ready")
    if not isinstance(entries, list):
        return _err_result("guest list payload was not a list", "serial_not_ready")
    entries = entries[:MAX_LIST_ENTRIES]
    return {
        "ok": True,
        "path": guest,
        "entries": entries,
        "count": len(entries),
        "via": "serial",
    }


def pull(guest_path: str, host_dest: Path) -> dict[str, Any]:
    """Copy a guest file into a confined host path via serial."""
    try:
        guest = sanitize_guest_path(guest_path, allow_dir=False)
    except ValueError as exc:
        return _err_result(str(exc), "invalid_args")

    dest = Path(host_dest)
    # tools.py already confined; re-check so direct callers stay safe.
    try:
        dest = confine(dest, home(), "dest")
    except PathError as exc:
        return _err_result(str(exc), getattr(exc, "code", "path_escape"))

    port = get_serial()
    if port is None:
        raise NotImplementedError(
            "templeos.files.pull: Slice D needs COM1 "
            "(bind_serial in tests, or vm.get_serial once Slice A lands)"
        )

    try:
        cmd, payload = _transact(port, CMD_PULL, guest.encode("utf-8"))
    except TimeoutError as exc:
        return _err_result(str(exc), "timeout")
    except Exception as exc:
        return _err_result(str(exc), "serial_not_ready")

    if cmd == CMD_ERR:
        return _err_result(
            payload.decode("utf-8", errors="replace") or "guest pull failed",
            "invalid_args",
        )
    if cmd != CMD_PULL_OK:
        return _err_result(
            f"unexpected serial reply cmd=0x{cmd:02x}",
            "serial_not_ready",
        )
    if len(payload) > MAX_FILE_BYTES:
        return _err_result(
            f"guest file exceeds {MAX_FILE_BYTES} bytes",
            "payload_too_large",
            "Pull a smaller file, or split it in the guest.",
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return {
        "ok": True,
        "guest_path": guest,
        "host_path": str(dest),
        "bytes": len(payload),
        "via": "serial",
    }


def push(host_src: Path, guest_path: str) -> dict[str, Any]:
    """Copy a confined host file into the guest via serial, or experimental FAT."""
    try:
        guest = sanitize_guest_path(guest_path, allow_dir=False)
    except ValueError as exc:
        return _err_result(str(exc), "invalid_args")

    src = Path(host_src)
    try:
        src = confine(src, home(), "src")
    except PathError as exc:
        return _err_result(str(exc), getattr(exc, "code", "path_escape"))

    port = get_serial()
    if port is None:
        raise NotImplementedError(
            "templeos.files.push: Slice D needs COM1 "
            "(bind_serial in tests, or vm.get_serial once Slice A lands); "
            "experimental FAT is _push_via_fat"
        )

    if not src.is_file():
        return _err_result(f"src is not a file: {src}", "invalid_args")
    size = src.stat().st_size
    if size > MAX_FILE_BYTES:
        return _err_result(
            f"src exceeds {MAX_FILE_BYTES} bytes",
            "payload_too_large",
            "Push a smaller file.",
        )
    data = src.read_bytes()

    if port is not None:
        payload = guest.encode("utf-8") + b"\x00" + data
        try:
            cmd, reply = _transact(port, CMD_PUSH, payload)
        except TimeoutError as exc:
            return _err_result(str(exc), "timeout")
        except Exception as exc:
            return _err_result(str(exc), "serial_not_ready")
        if cmd == CMD_ERR:
            return _err_result(
                reply.decode("utf-8", errors="replace") or "guest push failed",
                "invalid_args",
            )
        if cmd != CMD_PUSH_OK:
            return _err_result(
                f"unexpected serial reply cmd=0x{cmd:02x}",
                "serial_not_ready",
            )
        return {
            "ok": True,
            "guest_path": guest,
            "host_path": str(src),
            "bytes": size,
            "via": "serial",
        }

    # port was checked non-None above; keep for type checkers.
    return _err_result("serial not open", "serial_not_ready")


def _vm_appears_running() -> bool:
    try:
        from templeos import vm as vm_mod

        status = getattr(vm_mod, "status", None)
        if not callable(status):
            return False
        result = status()
        if isinstance(result, dict):
            return bool(result.get("running"))
    except NotImplementedError:
        return False
    except Exception:
        return False
    return False


def _push_via_fat(src: Path, guest: str, data: bytes) -> dict[str, Any]:
    """Build a small FAT image containing the file. Experimental.

    The bake-off could not see a hot-added FAT12 floppy as A: on TinkerOS.
    This path only runs when COM1 is down and the VM does not appear running.
    It never mounts the live RedSea qcow2.
    """
    if _vm_appears_running():
        return _err_result(
            "COM1 is not open while the VM is running; cannot use the FAT fallback.",
            "serial_not_ready",
            "Initialize Comm* and Xfer.HC, or stop the VM before an experimental FAT push.",
        )

    name = sanitize_guest_filename(Path(guest).name)
    out_dir = exchange_dir()
    img = out_dir / FAT_IMAGE_NAME
    staging = out_dir / "fat-staging"
    staging.mkdir(parents=True, exist_ok=True)
    staged = staging / name
    staged.write_bytes(data)

    mkfs = _which("mkfs.vfat") or _which("mkfs.fat")
    mcopy = _which("mcopy")
    if mkfs is None and mcopy is None:
        return _err_result(
            "FAT fallback needs mkfs.vfat or mtools (mcopy) on PATH.",
            "doctor_failed",
            "Install dosfstools or mtools, or use the serial Xfer path while the VM runs.",
            experimental=True,
        )

    try:
        img.write_bytes(b"\x00" * FAT_IMAGE_BYTES)
        env = child_env()
        if mkfs is not None:
            subprocess.run(
                [mkfs, "-n", "XFER", str(img)],
                check=True,
                env=env,
                capture_output=True,
                timeout=30,
            )
        else:
            # mformat from mtools
            mformat = _which("mformat")
            if mformat is None:
                return _err_result(
                    "mtools is present but mformat is missing.",
                    "doctor_failed",
                    "Install mtools, or mkfs.vfat from dosfstools.",
                    experimental=True,
                )
            subprocess.run(
                [mformat, "-i", str(img), "-v", "XFER", "::"],
                check=True,
                env=env,
                capture_output=True,
                timeout=30,
            )
        if mcopy is None:
            return _err_result(
                "mkfs.vfat worked but mcopy is missing; cannot place the file.",
                "doctor_failed",
                "Install mtools (mcopy).",
                experimental=True,
            )
        subprocess.run(
            [mcopy, "-o", "-i", str(img), str(staged), f"::{name}"],
            check=True,
            env=env,
            capture_output=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        return _err_result(
            f"FAT image build failed (exit {exc.returncode}).",
            "doctor_failed",
            "Check dosfstools/mtools; the FAT path is experimental.",
            experimental=True,
        )
    except Exception as exc:
        return _err_result(str(exc), "doctor_failed", experimental=True)

    return {
        "ok": True,
        "guest_path": guest,
        "host_path": str(src),
        "bytes": len(data),
        "via": "fat",
        "image": str(img),
        "experimental": True,
        "note": (
            "FAT floppy push is experimental: the bake-off did not see a hot-added "
            "FAT12 image as A: on the TinkerOS live CD. Attach the image only when "
            "the VM is stopped, then let the guest mount it if the flavor supports it."
        ),
    }


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)
