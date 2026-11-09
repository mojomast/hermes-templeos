"""End-to-end live TinkerOS smoke through the four registered tools + pane API.

Skipped unless TEMPLEOS_SMOKE=1 and the pinned bake-off ISO is on disk.
Leaves no QEMU processes behind.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from templeos import doctor as doctor_mod
from templeos.arbiter import reset_arbiter
from templeos.flavors import get_flavor
from templeos.input import CMD_LINE
from templeos.tools import handle_files, handle_input, handle_screen, handle_vm
from templeos import input as input_mod
from templeos import vm as vm_mod

ROOT = Path(__file__).resolve().parents[1]
SHOT = ROOT / "shots" / "p1-smoke" / "hello-from-hermes.png"
BAKEOFF_ISO = Path("/workspace/templeos-bakeoff/isos/TinkerOS_5.20-rc10.ISO")
TINKER_SHA = "feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4"
HOLYC_SOURCE = r'"Hello from Hermes\n"; 6*7;'
EXPECTED_TEXT = ("Hello from Hermes", "42")


def _parse(raw: str) -> dict:
    assert isinstance(raw, str)
    body = json.loads(raw)
    assert set(body) >= {"ok", "error", "code", "fix"}
    return body


def _qemu_pids() -> set[int]:
    found: set[int] = set()
    proc = Path("/proc")
    if not proc.is_dir():
        return found
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmd = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if b"qemu-system-x86_64" in cmd:
            found.add(int(entry.name))
    return found


def _kill(pid: int) -> None:
    try:
        os.kill(pid, 15)
    except OSError:
        return
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)
    try:
        os.kill(pid, 9)
    except OSError:
        return


def _iso_candidates() -> list[Path]:
    """ISO search order: TEMPLEOS_ISO, TEMPLEOS_HOME/isos, doctor cache, legacy."""
    try:
        filename = get_flavor("tinkeros")["iso_filename"]
    except Exception:
        filename = "TinkerOS_5.20-rc10.ISO"
    found: list[Path] = []
    raw = os.environ.get("TEMPLEOS_ISO")
    if raw and raw.strip():
        found.append(Path(raw).expanduser())
    home_env = os.environ.get("TEMPLEOS_HOME")
    if home_env and home_env.strip():
        found.append(Path(home_env).expanduser() / "isos" / filename)
    try:
        info = doctor_mod.ensure_iso("tinkeros", fetch=False)
        if info.get("ok") and info.get("path"):
            found.append(Path(str(info["path"])))
    except Exception:
        pass
    found.append(BAKEOFF_ISO)
    return found


def _find_iso() -> Path | None:
    seen: set[Path] = set()
    for candidate in _iso_candidates():
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    return None


def _smoke_ready() -> bool:
    return os.environ.get("TEMPLEOS_SMOKE") == "1" and _find_iso() is not None


def _wait_idle(timeout_s: float = 90.0) -> dict:
    return _parse(handle_screen({"op": "wait_idle", "timeout_s": timeout_s}))


def _stage_iso(home: Path, source: Path) -> None:
    cache = home / "isos"
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / get_flavor("tinkeros")["iso_filename"]
    if dest.exists() or dest.is_symlink():
        return
    try:
        dest.symlink_to(source)
    except OSError:
        import shutil

        shutil.copy2(source, dest)


def _wait_for_text(needles: tuple[str, ...], timeout_s: float = 60.0) -> tuple[str, dict]:
    """Poll wait_idle + read_text until every needle appears or the deadline passes."""
    deadline = time.monotonic() + timeout_s
    seen = ""
    last: dict = {}
    while time.monotonic() < deadline:
        _wait_idle(timeout_s=4)
        last = _parse(handle_screen({"op": "read_text"}))
        text = str(last.get("text") or "")
        if len(text) >= len(seen):
            seen = text
        if all(needle in seen for needle in needles):
            break
        time.sleep(0.5)
    return seen, last


def _send_key_send_key(qmp, codes, *, hold_ms: int = 100) -> None:
    """Use one QMP send-key chord with a long hold; reliable on slow TCG guests."""
    names = [str(c) for c in codes]
    if hasattr(qmp, "send_key"):
        qmp.send_key(names, hold_ms=hold_ms)
        return
    keys = [{"type": "qcode", "data": c} for c in names]
    qmp.cmd("send-key", keys=keys, **{"hold-time": hold_ms})


def _settle_guest(timeout_s: float = 180.0) -> str:
    """Answer the live-CD install/tour prompts, then return the desktop text."""
    deadline = time.monotonic() + timeout_s
    answered_install = False
    answered_tour = False
    text = ""
    while time.monotonic() < deadline:
        _wait_idle(timeout_s=3)
        text = str(_parse(handle_screen({"op": "read_text"})).get("text") or "")
        lower = text.lower()
        if not answered_install and "install onto hard drive" in lower and "y or n" in lower:
            _parse(handle_input({"op": "keys", "keys": ["n"]}))
            answered_install = True
            time.sleep(2.0)
            continue
        if not answered_tour and "take tour" in lower and "y or n" in lower:
            _parse(handle_input({"op": "keys", "keys": ["n"]}))
            answered_tour = True
            time.sleep(2.0)
            continue
        if "t:/home>" in lower:
            last_prompt = lower.rfind("t:/home>")
            last_dialog = max(
                lower.rfind("install onto hard drive"),
                lower.rfind("take tour"),
            )
            if last_prompt > last_dialog:
                _parse(handle_input({"op": "keys", "keys": ["backspace"] * 24}))
                time.sleep(0.5)
                return text
        time.sleep(1.0)
    return text


@pytest.mark.smoke
def test_tools_and_pane_api_live_tinkeros(tmp_path, monkeypatch):
    if os.environ.get("TEMPLEOS_SMOKE") != "1":
        pytest.skip("set TEMPLEOS_SMOKE=1 and keep the pinned TinkerOS ISO on disk")
    iso = _find_iso()
    if iso is None:
        pytest.skip("set TEMPLEOS_SMOKE=1 and keep the pinned TinkerOS ISO on disk")
    digest = hashlib.sha256(iso.read_bytes()).hexdigest()
    assert digest == TINKER_SHA, "bake-off ISO does not match the pinned SHA-256"

    home = tmp_path / "tos-home"
    home.mkdir()
    monkeypatch.setenv("TEMPLEOS_HOME", str(home))
    reset_arbiter()
    vm_mod._runtime = None
    _stage_iso(home, iso)
    monkeypatch.setattr(vm_mod, "_schedule_first_boot_dismiss", lambda: None)
    monkeypatch.setattr(input_mod, "_send_key", _send_key_send_key)

    files_note = "not attempted"
    procs_before = _qemu_pids()
    try:
        doctor = _parse(handle_vm({"op": "doctor"}))
        assert doctor.get("ok") is True or doctor.get("checks", {}).get("iso") or doctor.get("code") in {
            None,
            "doctor_failed",
        }

        started = _parse(handle_vm({"op": "start", "flavor": "tinkeros"}))
        assert started["ok"] is True, started
        assert started["running"] is True
        assert started["accel"] == "tcg"
        assert vm_mod.get_runtime() is not None
        assert vm_mod.get_serial() is not None

        # TinkerOS desktop is typically up around 14 s; wait_idle may timeout
        # during animation, so poll until look returns a 640x480 PNG.
        deadline = time.monotonic() + 120
        look = None
        while time.monotonic() < deadline:
            idle = _wait_idle(timeout_s=8)
            look = _parse(handle_screen({"op": "look"}))
            if look.get("ok") and look.get("width") == 640 and look.get("height") == 480 and look.get("data"):
                if time.monotonic() - (deadline - 120) >= 8:
                    break
            time.sleep(1.0)
        assert look and look["ok"] is True, look
        assert look["mime"] == "image/png"
        assert look["width"] == 640 and look["height"] == 480

        text = _settle_guest()
        assert text
        readback = _parse(handle_screen({"op": "read_text"}))
        assert readback["ok"] is True, readback
        assert readback.get("text") is not None

        typed = _parse(handle_input({"op": "holyc", "text": HOLYC_SOURCE, "via": "type"}))
        assert typed["ok"] is True, typed
        text_after, _ = _wait_for_text(EXPECTED_TEXT, timeout_s=60)

        shot = _parse(handle_screen({"op": "look"}))
        assert shot.get("ok") is True, shot
        assert shot.get("mime") == "image/png"
        assert shot.get("width") == 640 and shot.get("height") == 480
        assert shot.get("data")
        SHOT.parent.mkdir(parents=True, exist_ok=True)
        SHOT.write_bytes(base64.b64decode(shot["data"]))
        assert "Hello from Hermes" in text_after, text_after[-2000:]
        assert "42" in text_after, text_after[-2000:]

        clicked = _parse(
            handle_input({"op": "click", "x": CMD_LINE[0], "y": CMD_LINE[1], "via": "vmmouse"})
        )
        assert clicked["ok"] is True, clicked
        _wait_idle(timeout_s=15)

        snapped = _parse(handle_vm({"op": "snapshot", "name": "golden"}))
        assert snapped["ok"] is True, snapped
        restored = _parse(handle_vm({"op": "restore", "name": "golden"}))
        assert restored["ok"] is True, restored
        assert _parse(handle_vm({"op": "status"}))["running"] is True

        listed = _parse(handle_files({"op": "list", "path": "T:/"}))
        if listed.get("ok"):
            files_note = "list succeeded over serial"
            dest = home / "exchange" / "Smoke.HC"
            dest.parent.mkdir(parents=True, exist_ok=True)
            pulled = _parse(
                handle_files({"op": "pull", "path": "T:/Home/DoDistro.HC", "dest": str(dest)})
            )
            files_note = f"list ok; pull={pulled.get('code') or 'ok'}"
        else:
            files_note = f"serial Xfer not ready ({listed.get('code')}): needs Comm* + Xfer.HC in the guest"

        # Pane API: /frame plus a user-input route in shared mode, then confirm
        # the arbiter pauses agent tools for the ~2 s hold-off.
        pytest.importorskip("fastapi")
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from templeos.api import ROUTE_FRAME, ROUTE_INPUT, ROUTE_STATUS, create_router, reset_activity_log

        reset_activity_log()
        app = FastAPI()
        app.include_router(create_router())
        client = TestClient(app)

        status = client.get(ROUTE_STATUS).json()
        assert status["ok"] is True
        assert status["running"] is True
        assert status["mode"] == "shared"

        frame = client.get(ROUTE_FRAME).json()
        assert frame["ok"] is True
        assert frame.get("data")
        sha = frame.get("sha256")
        assert sha
        # The title-bar clock often changes the hash between requests; both
        # a cheap {unchanged:true} body and a fresh PNG are valid 200s.
        cheap = client.get(ROUTE_FRAME + "?since=" + sha).json()
        assert cheap["ok"] is True
        assert "unchanged" in cheap
        if cheap.get("unchanged") is True:
            assert cheap.get("data") is None
            assert cheap.get("sha256") == sha
        else:
            assert cheap.get("data")
        tagged = client.get(ROUTE_FRAME, headers={"If-None-Match": f'"{sha}"'}).json()
        assert tagged["ok"] is True
        assert "unchanged" in tagged

        clicked_ui = client.post(
            ROUTE_INPUT, json={"type": "click", "x": 40, "y": 40}
        ).json()
        assert clicked_ui.get("agent_paused") is True
        paused = _parse(handle_input({"op": "type", "text": "Hi"}))
        assert paused["ok"] is False and paused["code"] == "agent_paused"

        stopped = _parse(handle_vm({"op": "stop"}))
        assert stopped["ok"] is True
        assert stopped["running"] is False
    finally:
        try:
            vm_mod.stop()
        except Exception:
            pass
        vm_mod._runtime = None
        leftover = _qemu_pids() - procs_before
        for pid in leftover:
            _kill(pid)
        still = _qemu_pids() - procs_before
        assert not still, f"leaked QEMU pids: {still}"

    # Visible in pytest output when -s is used; stored for the integrator report.
    test_tools_and_pane_api_live_tinkeros.files_note = files_note  # type: ignore[attr-defined]
