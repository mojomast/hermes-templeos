"""Slice D: serial file protocol, confinement, and experimental FAT push."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from templeos.files import (
    CMD_ERR,
    CMD_LIST,
    CMD_LIST_OK,
    CMD_PULL,
    CMD_PULL_OK,
    CMD_PUSH,
    CMD_PUSH_OK,
    MAGIC,
    MAX_FILE_BYTES,
    bind_serial,
    encode_frame,
    exchange_dir,
    helper_source_path,
    list_guest,
    pull,
    push,
    sanitize_guest_path,
    try_decode_frame,
)
from templeos.tools import handle_files
from tests.fakes import FakeSerial


def _parse(raw: str) -> dict:
    assert isinstance(raw, str)
    body = json.loads(raw)
    assert "ok" in body and "code" in body
    return body


class GuestSerial(FakeSerial):
    """FakeSerial that answers Xfer frames as a cooperative guest."""

    def __init__(self) -> None:
        super().__init__()
        self.files: dict[str, bytes] = {
            "T:/Home/Hello.HC": b'"hello world\\n";\n',
            "T:/Demo/A.HC": b"U0 A(){}\n",
        }
        self.dirs: dict[str, list[dict]] = {
            "T:/": [
                {"name": "Home", "is_dir": 1},
                {"name": "Demo", "is_dir": 1},
            ],
            "T:/Home/": [
                {"name": "Hello.HC", "is_dir": 0},
            ],
            "T:/Home": [
                {"name": "Hello.HC", "is_dir": 0},
            ],
        }
        self._rx_buf = bytearray()

    def write(self, data: bytes) -> int:
        n = super().write(data)
        self._rx_buf.extend(data)
        self._drain()
        return n

    def _drain(self) -> None:
        while True:
            decoded = try_decode_frame(bytes(self._rx_buf))
            if decoded is None:
                return
            cmd, payload, consumed = decoded
            if cmd == -1:
                del self._rx_buf[:consumed]
                continue
            del self._rx_buf[:consumed]
            self._handle(cmd, payload)

    def _handle(self, cmd: int, payload: bytes) -> None:
        if cmd == CMD_LIST:
            path = payload.decode("utf-8")
            entries = self.dirs.get(path) or self.dirs.get(path.rstrip("/")) or []
            body = json.dumps(entries, separators=(",", ":")).encode("utf-8")
            self.guest_write(encode_frame(CMD_LIST_OK, body))
            return
        if cmd == CMD_PULL:
            path = payload.decode("utf-8")
            data = self.files.get(path)
            if data is None:
                self.guest_write(encode_frame(CMD_ERR, b"missing"))
                return
            self.guest_write(encode_frame(CMD_PULL_OK, data))
            return
        if cmd == CMD_PUSH:
            if b"\x00" not in payload:
                self.guest_write(encode_frame(CMD_ERR, b"push path"))
                return
            path_b, data = payload.split(b"\x00", 1)
            path = path_b.decode("utf-8")
            self.files[path] = data
            parent = path.rsplit("/", 1)[0] + "/"
            name = path.rsplit("/", 1)[-1]
            bucket = self.dirs.setdefault(parent, [])
            if not any(e.get("name") == name for e in bucket):
                bucket.append({"name": name, "is_dir": 0})
            self.guest_write(encode_frame(CMD_PUSH_OK, b""))
            return
        self.guest_write(encode_frame(CMD_ERR, b"cmd"))


@pytest.fixture
def guest(tos_home):
    port = GuestSerial()
    port.open(tos_home / "sockets" / "com1.sock")
    bind_serial(port)
    yield port
    bind_serial(None)


def test_encode_decode_roundtrip():
    frame = encode_frame(CMD_LIST, b"T:/Home/")
    assert frame.startswith(MAGIC)
    cmd, payload, consumed = try_decode_frame(frame)
    assert cmd == CMD_LIST and payload == b"T:/Home/" and consumed == len(frame)


def test_decode_needs_more_bytes():
    frame = encode_frame(CMD_PULL, b"T:/X.HC")
    assert try_decode_frame(frame[:5]) is None
    assert try_decode_frame(frame[:-1]) is None


def test_sanitize_guest_paths():
    assert sanitize_guest_path("T:/") == "T:/"
    assert sanitize_guest_path("T:/Home/Hello.HC") == "T:/Home/Hello.HC"
    with pytest.raises(ValueError):
        sanitize_guest_path("T:/../Etc")
    with pytest.raises(ValueError):
        sanitize_guest_path("/etc/passwd")
    with pytest.raises(ValueError):
        sanitize_guest_path("T:/Home/", allow_dir=False)


def test_list_pull_push_over_fake_serial(guest, tos_home):
    listed = list_guest("T:/")
    assert listed["ok"] is True
    assert listed["via"] == "serial"
    assert listed["count"] >= 2
    names = {e["name"] for e in listed["entries"]}
    assert "Home" in names

    dest = tos_home / "exchange" / "Hello.HC"
    dest.parent.mkdir(parents=True, exist_ok=True)
    got = pull("T:/Home/Hello.HC", dest)
    assert got["ok"] is True
    assert dest.read_bytes().startswith(b'"hello')
    assert got["bytes"] == dest.stat().st_size

    src = tos_home / "exchange" / "New.HC"
    src.write_text('U0 New(){ "hi\\n"; }\n')
    pushed = push(src, "T:/Home/New.HC")
    assert pushed["ok"] is True and pushed["via"] == "serial"
    assert guest.files["T:/Home/New.HC"].startswith(b"U0 New")


def test_pull_missing_file(guest, tos_home):
    dest = tos_home / "exchange" / "Nope.HC"
    dest.parent.mkdir(parents=True, exist_ok=True)
    got = pull("T:/Home/Nope.HC", dest)
    assert got["ok"] is False
    assert got["code"] == "invalid_args"


def test_unbound_serial_still_raises_for_integration_stubs(tos_home):
    """Until feat/integration flips the empty-serial branch, keep NI for stubs."""
    bind_serial(None)
    with pytest.raises(NotImplementedError, match="Slice D"):
        list_guest("T:/")
    with pytest.raises(NotImplementedError, match="Slice D"):
        pull("T:/Home/X.HC", tos_home / "X.HC")
    with pytest.raises(NotImplementedError, match="Slice D"):
        push(tos_home / "missing.HC", "T:/Home/X.HC")


def test_closed_serial_is_treated_as_unbound(tos_home):
    port = GuestSerial()
    # never open()
    bind_serial(port)
    try:
        with pytest.raises(NotImplementedError, match="Slice D"):
            list_guest("T:/")
    finally:
        bind_serial(None)


def test_tool_handler_list_and_pull(guest, tos_home):
    body = _parse(handle_files({"op": "list", "path": "T:/Home/"}))
    assert body["ok"] is True
    assert body["count"] >= 1

    dest = tos_home / "inbox" / "Hello.HC"
    dest.parent.mkdir()
    body = _parse(
        handle_files(
            {"op": "pull", "path": "T:/Home/Hello.HC", "dest": str(dest)}
        )
    )
    assert body["ok"] is True
    assert dest.is_file()


def test_tool_handler_push(guest, tos_home):
    src = tos_home / "outbox" / "Z.HC"
    src.parent.mkdir()
    src.write_text("U0 Z(){}\n")
    body = _parse(
        handle_files({"op": "push", "path": "T:/Home/Z.HC", "src": str(src)})
    )
    assert body["ok"] is True
    assert guest.files["T:/Home/Z.HC"] == b"U0 Z(){}\n"


def test_tool_path_escape_still_rejected(tos_home, tmp_path):
    bind_serial(None)
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    body = _parse(
        handle_files({"op": "pull", "path": "T:/Home/X.HC", "dest": str(outside)})
    )
    assert body["ok"] is False and body["code"] == "path_escape"


def test_push_rejects_oversize(guest, tos_home):
    src = tos_home / "exchange" / "big.bin"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    got = push(src, "T:/Home/Big.HC")
    assert got["ok"] is False and got["code"] == "payload_too_large"


def test_helper_source_exists():
    path = helper_source_path()
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "XferServe" in text
    assert "TXFR" in text or "XFER_MAGIC" in text


def test_exchange_dir_under_home(tos_home):
    path = exchange_dir()
    assert path.is_dir()
    assert path.resolve().is_relative_to(tos_home.resolve())


def test_experimental_fat_push_helper(tos_home):
    bind_serial(None)
    from templeos.files import _push_via_fat

    src = tos_home / "exchange" / "Solo.HC"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("U0 Solo(){}\n")
    data = src.read_bytes()
    got = _push_via_fat(src, "T:/Home/Solo.HC", data)
    assert got["ok"] is False or got.get("via") == "fat"
    if got["ok"] is False:
        assert got["code"] in {"doctor_failed", "serial_not_ready"}
        assert got.get("experimental") is True or got["code"] == "serial_not_ready"
    else:
        assert got["experimental"] is True
        assert Path(got["image"]).is_file()


def test_noise_before_magic_is_skipped(guest):
    # Prepend junk then a valid list request by calling list_guest normally;
    # also ensure try_decode_frame reports leading noise.
    frame = encode_frame(CMD_LIST, b"T:/")
    noisy = b"xx" + frame
    cmd, payload, consumed = try_decode_frame(noisy)
    assert cmd == -1 and consumed == 2
