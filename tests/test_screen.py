"""Slice B screen: glyphs, hashes, wait_idle, look, and a live TinkerOS smoke."""

from __future__ import annotations

import io
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from templeos.envsafe import child_env
from templeos.screen import (
    bind,
    capture_image,
    encode_jpeg,
    encode_png,
    frame_hash,
    glyph_read,
    glyph_read_ex,
    hash_image,
    look,
    read_text,
    unbind,
    wait_idle,
)
from tests.fakes import MIN_PNG, FakeQMP, FakeSerial

ROOT = Path(__file__).resolve().parents[1]
FRAMES = Path(__file__).parent / "fixtures" / "frames"
EXPECTED = json.loads((FRAMES / "expected.json").read_text())

BAKEOFF = Path("/workspace/templeos-bakeoff")
SMOKE_DISK = Path(os.environ.get("TEMPLEOS_SMOKE_DISK") or BAKEOFF / "disks" / "tinkeros.qcow2")
SMOKE_ISO = Path(os.environ.get("TEMPLEOS_SMOKE_ISO") or BAKEOFF / "isos" / "TinkerOS_5.20-rc10.ISO")
QEMU_BIN = os.environ.get("TEMPLEOS_QEMU") or "qemu-system-x86_64"


@pytest.fixture(autouse=True)
def _reset_runtime():
    unbind()
    yield
    unbind()


def _png_bytes(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _bind(tos_home, framebuffer: bytes | None = None, *, flavor: str = "tinkeros", serial=None, abs_mouse: bool = True):
    qmp = FakeQMP(abs_mouse=abs_mouse)
    qmp.connect(tos_home / "qmp.sock")
    if framebuffer is not None:
        qmp.framebuffer = framebuffer
    bind(qmp=qmp, serial=serial, flavor=flavor, state_dir=tos_home, type_delay_s=0)
    return qmp


def test_unbound_look_returns_vm_not_running():
    body = look()
    assert body["ok"] is False
    assert body["code"] == "vm_not_running"
    with pytest.raises(ValueError, match="image"):
        glyph_read(b"")


def test_glyph_fixtures_contain_expected_needles():
    from PIL import Image

    report = {}
    for name, spec in EXPECTED.items():
        path = FRAMES / name
        assert path.is_file(), name
        im = Image.open(path).convert("RGB")
        result = glyph_read_ex(im, flavor=spec["flavor"])
        text = result["text"]
        missing = [n for n in spec["needles"] if n not in text]
        report[name] = {
            "confidence": result["confidence"],
            "cells": result["cells"],
            "matched": result["matched"],
            "exact": result["exact"],
            "missing": missing,
        }
        if spec.get("optional") and missing:
            pytest.xfail(f"{name} optional needles missing: {missing}")
        assert missing == [], f"{name} missing {missing}; confidence={result['confidence']}"
        # Also exercise the Path/bytes entry point.
        assert all(n in glyph_read(path, flavor=spec["flavor"]) for n in spec["needles"] if not spec.get("optional"))
    # Keep a compact accuracy record in the assertion message if something regresses.
    assert all(row["confidence"] >= 0.5 for name, row in report.items() if not EXPECTED[name].get("optional") and row["cells"])


def test_glyph_accuracy_numbers_on_tinkeros_and_templeos():
    from PIL import Image

    rows = []
    for name, spec in EXPECTED.items():
        im = Image.open(FRAMES / name).convert("RGB")
        result = glyph_read_ex(im, flavor=spec["flavor"])
        acc = (result["matched"] / result["cells"]) if result["cells"] else 1.0
        rows.append((name, acc, result["exact"], result["matched"], result["cells"], result["confidence"]))
    # TinkerOS / TempleOS FontStd should stay in the previously measured band.
    by_name = {r[0]: r for r in rows}
    assert by_name["tinkeros-holyc-prompt.png"][1] >= 0.70
    assert by_name["tinkeros-mouse-click.png"][1] >= 0.80
    assert by_name["templeos-holyc-prompt.png"][1] >= 0.68
    # Hello is exact on the two HolyC prompt shots.
    for name in ("tinkeros-holyc-prompt.png", "templeos-holyc-prompt.png"):
        text = glyph_read(FRAMES / name, flavor=EXPECTED[name]["flavor"])
        assert "Hello" in text
        assert '"Hello' in text or "Hello" in text


def test_crop_hash_ignores_the_clock_row(tos_home):
    from PIL import Image

    def frame(clock_color: tuple[int, int, int]) -> "Image.Image":
        im = Image.new("RGB", (640, 480), (0, 0, 80))
        # Title bar (hash_crop starts at y=24).
        bar = Image.new("RGB", (640, 24), (20, 20, 20))
        im.paste(bar, (0, 0))
        im.putpixel((12, 6), clock_color)
        # Stable body.
        body = Image.new("RGB", (520, 446), (0, 0, 160))
        im.paste(body, (0, 24))
        return im

    a = frame((255, 255, 0))
    b = frame((0, 255, 0))
    ha = hash_image(a, flavor="tinkeros")
    hb = hash_image(b, flavor="tinkeros")
    assert ha["sha256"] == hb["sha256"]
    assert ha["full_sha256"] != hb["full_sha256"]
    assert ha["crop"]["y"] == 24

    qmp = _bind(tos_home, _png_bytes(a), flavor="tinkeros")
    first = frame_hash()
    qmp.framebuffer = _png_bytes(b)
    second = frame_hash()
    assert first["ok"] and second["ok"]
    assert first["sha256"] == second["sha256"]
    assert first["full_sha256"] != second["full_sha256"]


def test_wait_idle_succeeds_when_hash_is_stable(tos_home):
    from PIL import Image

    stable = _png_bytes(Image.new("RGB", (64, 64), (10, 20, 30)))
    qmp = _bind(tos_home, stable)
    # Alternate once, then stay put so the cropped hash can settle.
    frames = [
        _png_bytes(Image.new("RGB", (64, 64), (1, 0, 0))),
        _png_bytes(Image.new("RGB", (64, 64), (0, 1, 0))),
        stable,
        stable,
        stable,
        stable,
        stable,
        stable,
    ]
    state = {"i": 0}
    orig = qmp.screendump

    def sequenced(dest: Path, fmt: str = "png") -> Path:
        qmp.framebuffer = frames[min(state["i"], len(frames) - 1)]
        state["i"] += 1
        return orig(dest, fmt)

    qmp.screendump = sequenced  # type: ignore[method-assign]
    result = wait_idle(timeout_s=2.0, stable_ms=40, crop={"x": 0, "y": 0, "w": 64, "h": 64})
    assert result["ok"] is True
    assert result["sha256"]
    assert result["waited_s"] >= 0


def test_wait_idle_times_out_when_the_frame_keeps_changing(tos_home):
    from PIL import Image

    a = _png_bytes(Image.new("RGB", (32, 32), (1, 0, 0)))
    b = _png_bytes(Image.new("RGB", (32, 32), (0, 0, 1)))
    qmp = _bind(tos_home, a)
    state = {"flip": False}
    orig = qmp.screendump

    def flip(dest: Path, fmt: str = "png") -> Path:
        state["flip"] = not state["flip"]
        qmp.framebuffer = a if state["flip"] else b
        return orig(dest, fmt)

    qmp.screendump = flip  # type: ignore[method-assign]
    result = wait_idle(timeout_s=0.25, stable_ms=200, crop={"x": 0, "y": 0, "w": 32, "h": 32})
    assert result["ok"] is False
    assert result["code"] == "timeout"


def test_look_returns_png_and_caption_from_glyphs(tos_home):
    frame = (FRAMES / "tinkeros-holyc-prompt.png").read_bytes()
    _bind(tos_home, frame, flavor="tinkeros")
    dest = tos_home / "frames" / "out.png"
    result = look(dest=dest)
    assert result["ok"] is True
    assert result["mime"] == "image/png"
    assert result["width"] == 640 and result["height"] == 480
    assert result["data"] and result["sha256"]
    assert dest.is_file()
    assert "Hello" in (result.get("caption") or "")
    assert result.get("crop_sha256")


def test_look_accepts_png_written_as_ppm_filename(tos_home):
    # FakeQMP writes MIN_PNG regardless of format=ppm.
    _bind(tos_home, MIN_PNG)
    im = capture_image()
    assert im.size == (1, 1)
    result = look()
    assert result["ok"] is True
    assert result["mime"] == "image/png"
    assert result["caption"]


def test_encode_png_and_jpeg_respect_size_caps():
    from PIL import Image

    im = Image.new("RGB", (400, 400), (12, 34, 56))
    # Add noise so PNG cannot compress to a tiny palette.
    pixels = im.load()
    for y in range(0, 400, 3):
        for x in range(0, 400, 3):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, (x + y) % 256)
    data, out = encode_png(im, max_bytes=8 * 1024)
    assert len(data) <= 8 * 1024
    assert out.size[0] <= im.size[0]
    jpeg = encode_jpeg(im, quality=85, max_bytes=8 * 1024)
    assert len(jpeg) <= 8 * 1024
    assert jpeg[:2] == b"\xff\xd8"


def test_read_text_prefers_serial_when_connected(tos_home):
    serial = FakeSerial()
    serial.open(tos_home / "com1.sock")
    serial.guest_write(b"BAKEOFF-TINK\nHello\n")
    _bind(tos_home, MIN_PNG, serial=serial)
    result = read_text()
    assert result["ok"] is True
    assert result["source"] == "serial"
    assert "Hello" in result["text"]


def test_read_text_falls_back_to_glyphs(tos_home):
    serial = FakeSerial()
    serial.open(tos_home / "com1.sock")
    # Connected but silent: use glyphs.
    frame = (FRAMES / "tinkeros-mouse-click.png").read_bytes()
    _bind(tos_home, frame, flavor="tinkeros", serial=serial)
    result = read_text()
    assert result["ok"] is True
    assert result["source"] == "glyphs"
    assert "Command Line Overview" in result["text"]
    assert result["confidence"] >= 0.8


def test_read_text_ignores_serial_that_was_never_opened(tos_home):
    serial = FakeSerial()
    serial.guest_write(b"dropped")
    assert serial.dropped == b"dropped"
    frame = (FRAMES / "templeos-holyc-prompt.png").read_bytes()
    _bind(tos_home, frame, flavor="templeos", serial=serial)
    result = read_text()
    assert result["source"] == "glyphs"
    assert "TempleOS" in result["text"]


# ---------------------------------------------------------------------------
# Live smoke (skipped unless TEMPLEOS_SMOKE=1)
# ---------------------------------------------------------------------------



def _click_target_from_text(text_rows, needle: str | None = None, *, cell: int = 8, origin=(0, 0)):
    """Return a pixel near the center of the first Help-line Cmd line link.

    Prefer the first 'Quick Start:' on the row so a later duplicate window
    (or a missing L in 'Cmd  ine') cannot steal the click.
    """
    ox, oy = origin
    for row, line in enumerate(text_rows or []):
        prefix = line.find("Quick Start:")
        if prefix >= 0:
            col = prefix + len("Quick Start:") + 1  # C in Cmd
            width = len("Cmd line")
            x = ox + col * cell + (width * cell) // 2
            y = oy + row * cell + cell // 2
            return x, y, row, col
        for item in (needle, "Cmd line", "Cmd Line"):
            if not item:
                continue
            col = line.find(item)
            if col < 0:
                continue
            x = ox + col * cell + (len(item) * cell) // 2
            y = oy + row * cell + cell // 2
            return x, y, row, col
    return None


class _LiveQMP:
    """Minimal QMP client for the smoke test only (Slice A's qmp.py is a stub)."""

    def __init__(self, path: Path, timeout: float = 30.0) -> None:
        self.path = path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.buf = b""
        deadline = time.time() + timeout
        last: Exception | None = None
        while time.time() < deadline:
            try:
                self.sock.connect(str(path))
                break
            except OSError as exc:
                last = exc
                time.sleep(0.1)
        else:
            raise RuntimeError(f"QMP connect failed: {path}: {last}")
        self._read_obj()
        self.cmd("qmp_capabilities")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def _read_obj(self) -> dict[str, Any]:
        while True:
            if b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                if not line.strip():
                    continue
                obj = json.loads(line.decode())
                if "event" in obj:
                    continue
                return obj
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("QMP socket closed")
            self.buf += chunk

    def cmd(self, execute: str, **arguments: Any) -> dict[str, Any]:
        msg: dict[str, Any] = {"execute": execute}
        if arguments:
            msg["arguments"] = arguments
        self.sock.sendall((json.dumps(msg) + "\n").encode())
        resp = self._read_obj()
        if "error" in resp:
            raise RuntimeError(f"QMP {execute} error: {resp['error']}")
        return resp

    def hmp(self, command: str) -> str:
        return str(self.cmd("human-monitor-command", **{"command-line": command}).get("return", ""))

    def screendump(self, dest: Path, fmt: str = "ppm") -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.cmd("screendump", filename=str(dest), format=fmt)
        return dest

    def send_key(self, codes: list[str], *, hold_ms: int = 80) -> None:
        keys = [{"type": "qcode", "data": c} for c in codes]
        self.cmd("send-key", keys=keys, **{"hold-time": hold_ms})

    def input_send_event(self, events: list[dict[str, Any]]) -> None:
        self.cmd("input-send-event", events=events)


def _terminate(proc: subprocess.Popen[Any] | None, qmp: _LiveQMP | None = None) -> None:
    if qmp is not None:
        try:
            qmp.cmd("quit")
        except Exception:
            pass
        qmp.close()
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass


@pytest.mark.smoke
@pytest.mark.skipif(os.environ.get("TEMPLEOS_SMOKE") != "1", reason="set TEMPLEOS_SMOKE=1")
def test_smoke_tinkeros_types_hello_and_clicks_cmd_line(tos_home, tmp_path):
    """Boot the bake-off TinkerOS snapshot, type Hello, read it, click Cmd Line."""
    if not SMOKE_DISK.is_file():
        pytest.skip(f"TinkerOS disk not found: {SMOKE_DISK}")
    if not SMOKE_ISO.is_file():
        pytest.skip(f"TinkerOS ISO not found: {SMOKE_ISO}")

    from templeos.input import click, type_text
    from templeos.screen import bind as bind_rt

    work = tmp_path / "smoke"
    work.mkdir()
    disk = work / "tinkeros.qcow2"
    # Full copy: loadvm snapshots live on the qcow2, not on an overlay.
    subprocess.run(["cp", "--sparse=always", str(SMOKE_DISK), str(disk)], check=True)
    socks = work / "socks"
    socks.mkdir()
    qmp_path = socks / "qmp.sock"
    vnc_path = socks / "vnc.sock"
    com1_path = socks / "com1.sock"
    log_path = work / "qemu.log"

    argv = [
        QEMU_BIN,
        "-name",
        "templeos-slice-b-smoke",
        "-machine",
        "pc,kernel-irqchip=off",
        "-accel",
        "tcg",
        "-cpu",
        "qemu64",
        "-m",
        "2G",
        "-smp",
        "1",
        "-vga",
        "std",
        "-display",
        "none",
        "-nic",
        "none",
        "-cdrom",
        str(SMOKE_ISO),
        "-boot",
        "order=d,menu=on",
        "-drive",
        f"file={disk},format=qcow2,if=ide,index=1,media=disk",
        "-qmp",
        f"unix:{qmp_path},server=on,wait=off",
        "-vnc",
        f"unix:{vnc_path}",
        "-serial",
        f"unix:{com1_path},server=on,wait=off",
    ]
    env = child_env()
    with log_path.open("wb") as log:
        proc = subprocess.Popen(
            argv,
            env=env,
            cwd=str(work),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    qmp = None
    try:
        qmp = _LiveQMP(qmp_path, timeout=30.0)
        # Do not send ESC after loadvm: that closed the session window in the bake-off.
        qmp.hmp("loadvm bake1")
        qmp.hmp("cont")
        bind_rt(qmp=qmp, flavor="tinkeros", state_dir=tos_home, type_delay_s=0.09)
        time.sleep(0.4)
        idle = wait_idle(timeout_s=8.0, stable_ms=200)
        # Clock-cropped idle is best-effort on a live guest.
        assert idle.get("sha256") or idle.get("code") in {"timeout", None}

        typed = type_text('"Hello\\n";', delay_s=0.09)
        assert typed["ok"] is True
        time.sleep(0.6)
        wait_idle(timeout_s=5.0, stable_ms=200)
        text = read_text()
        assert text["ok"] is True
        assert "Hello" in (text.get("text") or ""), text.get("text")

        # The bake-off used (255, 51) on a clean Help line. This snapshot can
        # have more windows, so locate "Cmd line" on the current glyph grid.
        located = _click_target_from_text(text.get("rows") or (text.get("text") or "").splitlines(), "Cmd line")
        if located is None:
            located = _click_target_from_text(text.get("rows") or [], "Cmd Line")
        assert located is not None, "could not find Cmd line on the current frame"
        cx, cy, row, col = located
        clicked = click(int(cx), int(cy), button="left", via="vmmouse", flavor="tinkeros")
        assert clicked["ok"] is True
        assert clicked.get("via") == "vmmouse"
        time.sleep(1.2)
        wait_idle(timeout_s=5.0, stable_ms=200)
        after = read_text()
        assert after["ok"] is True
        # The bake-off click on Cmd Line opened Command Line Overview.
        assert "Command Line Overview" in (after.get("text") or ""), (
            f"clicked Cmd line at ({cx},{cy}) row={row} col={col} abs={clicked.get('abs')!r}\n"
            + (after.get("text") or "")
        )
    finally:
        unbind()
        _terminate(proc, qmp)
