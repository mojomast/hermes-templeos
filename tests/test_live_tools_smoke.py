"""End-to-end live TinkerOS smoke through the four registered tools + pane API.

Skipped unless TEMPLEOS_SMOKE=1 and the pinned bake-off ISO is on disk.
Leaves no QEMU processes behind.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import pytest

from templeos.arbiter import reset_arbiter
from templeos.flavors import get_flavor
from templeos.input import CMD_LINE
from templeos.tools import handle_files, handle_input, handle_screen, handle_vm
from templeos import vm as vm_mod

TINKER_SHA = "feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4"
HOLYC_ONE_LINER = '"Hello from Hermes\\n"; 6*7;'
SHOT_PATH = Path(__file__).resolve().parents[1] / "shots" / "p4-tcg-shift" / "hello-from-hermes.png"


def _iso_candidates() -> list[Path]:
    """Portable ISO lookup: env override, doctor cache, TEMPLEOS_HOME, legacy."""
    name = get_flavor("tinkeros")["iso_filename"]
    found: list[Path] = []
    env_iso = os.environ.get("TEMPLEOS_ISO")
    if env_iso:
        found.append(Path(env_iso).expanduser())
    try:
        from templeos.doctor import ensure_iso

        info = ensure_iso("tinkeros", fetch=False)
        if info.get("path"):
            found.append(Path(info["path"]))
    except Exception:
        pass
    try:
        from templeos.paths import isos_dir

        found.append(isos_dir() / name)
    except Exception:
        pass
    legacy_env = os.environ.get("TEMPLEOS_LEGACY_ISO_DIR")
    if legacy_env:
        found.append(Path(legacy_env).expanduser() / name)
    # Legacy bake-off caches sit beside the checkout; walk ancestors so the
    # lookup stays portable and never hardcodes a host path.
    cwd = Path.cwd()
    for parent in (cwd, *cwd.parents):
        found.append(parent / "templeos-bakeoff" / "isos" / name)
    return found


def _find_iso() -> Path | None:
    seen: set[Path] = set()
    for candidate in _iso_candidates():
        try:
            path = candidate.expanduser()
        except Exception:
            continue
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            return path
    return None


def _parse(raw: str) -> dict:
    assert isinstance(raw, str)
    body = json.loads(raw)
    assert set(body) >= {"ok", "error", "code", "fix"}
    return body


def _one_liner_visible(text: str) -> bool:
    """True only for real output, not the echoed source or memory addresses.

    A successful run has a line that is just ``Hello from Hermes`` plus the
    HolyC result ``ans=0x0000002A=42`` (6*7). Requiring both avoids passing on
    the typed line or on the existing 6D57B428-style menu address.
    """
    printed = any(line.strip() == "Hello from Hermes" for line in text.splitlines())
    result = re.search(r"ans=0x0*2A=42\b", text) is not None
    return printed and result


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


def _smoke_ready() -> bool:
    return os.environ.get("TEMPLEOS_SMOKE") == "1" and _find_iso() is not None


def _wait_idle(timeout_s: float = 90.0) -> dict:
    return _parse(handle_screen({"op": "wait_idle", "timeout_s": timeout_s}))


def _stage_iso(home: Path, iso: Path) -> None:
    cache = home / "isos"
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / get_flavor("tinkeros")["iso_filename"]
    if dest.exists() or dest.is_symlink():
        return
    try:
        dest.symlink_to(iso)
    except OSError:
        import shutil

        shutil.copy2(iso, dest)


@pytest.mark.smoke
def test_tools_and_pane_api_live_tinkeros(tmp_path, monkeypatch):
    iso = _find_iso()
    if not _smoke_ready() or iso is None:
        pytest.skip("set TEMPLEOS_SMOKE=1 and keep the pinned TinkerOS ISO on disk")
    digest = hashlib.sha256(iso.read_bytes()).hexdigest()
    assert digest == TINKER_SHA, "bake-off ISO does not match the pinned SHA-256"

    home = tmp_path / "tos-home"
    home.mkdir()
    monkeypatch.setenv("TEMPLEOS_HOME", str(home))
    reset_arbiter()
    vm_mod._runtime = None
    _stage_iso(home, iso)

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

        from templeos.screen import capture_image, glyph_read_ex

        # TinkerOS desktop is typically up around 14 s; wait_idle may timeout
        # during animation, so poll until look returns a 640x480 PNG and the
        # 8x8 glyph matcher can see the T:/Home prompt. A blank early frame is
        # not enough under load (the full smoke suite boots a VM twice).
        deadline = time.monotonic() + 150
        look = None
        boot_text = ""
        while time.monotonic() < deadline:
            _wait_idle(timeout_s=8)
            look = _parse(handle_screen({"op": "look"}))
            boot_im = capture_image()
            boot_text = str(glyph_read_ex(boot_im, flavor="tinkeros").get("text") or "")
            if (
                look.get("ok")
                and look.get("width") == 640
                and look.get("height") == 480
                and look.get("data")
                and "home>" in boot_text.lower()
            ):
                break
            time.sleep(1.5)
        assert look and look["ok"] is True, look
        assert look["mime"] == "image/png"
        assert look["width"] == 640 and look["height"] == 480
        assert "home>" in boot_text.lower(), boot_text[-1500:]

        # Companion observer hooks must fire against the live guest: greet on
        # session start, typing while a templeos_* tool call is in flight, and
        # celebrate once the same call reports success. The hooks are the same
        # callbacks Hermes registers through plugin.yaml.
        from templeos import companion

        companion.reset_state()
        hooks = companion._make_hooks()
        hooks["on_session_start"]()
        assert companion.resolve_animation() == "greet"
        assert companion.snapshot()["reason"] == "session_start"
        hooks["pre_tool_call"](tool="templeos_screen", args={"op": "look"})
        assert companion.resolve_animation() == "typing"
        hooked_look = _parse(handle_screen({"op": "look"}))
        assert hooked_look["ok"] is True, hooked_look
        assert hooked_look["width"] == 640 and hooked_look["height"] == 480
        assert companion.resolve_animation() == "typing", "typing must hold while the tool is in flight"
        hooks["post_tool_call"](tool="templeos_screen", ok=hooked_look["ok"])
        assert companion.resolve_animation() == "celebrate_short"
        assert companion.snapshot()["reason"] == "tool_ok"

        text = _parse(handle_screen({"op": "read_text"}))
        assert text["ok"] is True, text
        assert text.get("text") is not None

        # The production input path must put both the string output and the
        # evaluated 6*7 result on the guest screen; read it back from a
        # screendump with the built-in 8x8 glyph matcher. TCG occasionally
        # garbles a long line, so allow a few clean retries at the prompt.
        shot_im = None
        ocr_text = ""
        for _attempt in range(3):
            # Clear AutoComplete focus so the first shifted character lands.
            _parse(handle_input({"op": "keys", "keys": ["esc"]}))
            time.sleep(0.6)
            typed = _parse(handle_input({"op": "holyc", "text": HOLYC_ONE_LINER, "via": "type"}))
            assert typed["ok"] is True, typed
            assert typed.get("via") == "type", typed
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                _wait_idle(timeout_s=5)
                shot_im = capture_image()
                ocr = glyph_read_ex(shot_im, flavor="tinkeros")
                ocr_text = str(ocr.get("text") or "")
                if _one_liner_visible(ocr_text):
                    break
                time.sleep(1.0)
            if _one_liner_visible(ocr_text):
                break
        if shot_im is not None:
            SHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            shot_im.save(SHOT_PATH, format="PNG")
        assert _one_liner_visible(ocr_text), ocr_text[-2500:]

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

        from templeos.api import (
            ROUTE_COMPANION,
            ROUTE_FRAME,
            ROUTE_INPUT,
            ROUTE_STATUS,
            create_router,
            reset_activity_log,
        )

        reset_activity_log()
        app = FastAPI()
        app.include_router(create_router())
        client = TestClient(app)

        status = client.get(ROUTE_STATUS).json()
        assert status["ok"] is True
        assert status["running"] is True
        assert status["mode"] == "shared"
        assert status["companion"]["enabled"] is True
        assert status["companion"]["character"] == "terry"
        assert status["companion"]["tribute"] is True

        # Pane speech: POST /companion with a caller-supplied line. The dock
        # reserves a bubble lane wide enough for this text; the pane renders it
        # in shots/terry/terry-hermes-dark.png without clipping.
        said = client.post(ROUTE_COMPANION, json={"say": "Hello from Hermes"}).json()
        assert said["ok"] is True, said
        assert said["companion"]["speech"]["active"] is True
        assert said["companion"]["speech"]["text"] == "Hello from Hermes"
        echoed = client.get(ROUTE_COMPANION).json()
        assert echoed["companion"]["speech"]["text"] == "Hello from Hermes"
        spoken_status = client.get(ROUTE_STATUS).json()
        assert spoken_status["companion"]["speech"]["active"] is True
        assert spoken_status["companion"]["speech"]["text"] == "Hello from Hermes"

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
