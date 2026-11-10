"""Terry companion observers for the TempleOS Desktop pane.

Original fan-made tribute inspired by Terry A. Davis. No official TempleOS
affiliation is claimed. No invented quotes.

Enabled by default (tribute). Disable with settings companion=off or
TEMPLEOS_COMPANION=off. The pane hide toggle only hides the sprite; it does
not unregister hooks. No new agent tools — state is exposed on /status and
driven by Hermes hooks plus a few pane API signals.
"""

from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
import threading
import time
from pathlib import Path
from typing import Any, Callable

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = PLUGIN_ROOT / "desktop" / "assets" / "companion" / "terry"
V4_ROOT = ASSETS_ROOT / "v4"

ENV_COMPANION = "TEMPLEOS_COMPANION"
COSTUMES = ("base", "cowboy", "wizard", "chef")
DEFAULT_COSTUME = "base"

# Atlas row names (must match modular/out/atlas.json).
ANIM_IDLE = "idle"
ANIM_WAVING = "waving"
ANIM_WAITING = "waiting"
ANIM_RUNNING = "running"
ANIM_RUNNING_RIGHT = "running-right"
ANIM_RUNNING_LEFT = "running-left"
ANIM_JUMPING = "jumping"
ANIM_FAILED = "failed"
ANIM_REVIEW = "review"
ANIM_VM_BOOTING = "vm_booting"
ANIM_CELEBRATE = "celebrate_short"
ANIM_GREET = "greet"
ANIM_NOD = "nod"
ANIM_STRETCH = "stretch"
ANIM_RELIEVED = "relieved"
ANIM_TYPING = "typing"
ANIM_TALKING = "talking"
ANIM_SMOKING = "smoking"
ANIM_EXHALING = "exhaling"
ANIM_DANCE = "dance"
# Pre-baked v2 clip names (desktop/assets/companion/terry/clips/).
RICH_CLIPS = (
    ANIM_VM_BOOTING,
    ANIM_CELEBRATE,
    ANIM_GREET,
    ANIM_NOD,
    ANIM_STRETCH,
    ANIM_RELIEVED,
    ANIM_TYPING,
    ANIM_TALKING,
    ANIM_SMOKING,
    ANIM_EXHALING,
    ANIM_DANCE,
)

ONESHOT_S = {
    ANIM_WAVING: 2.2,
    ANIM_JUMPING: 1.3,
    ANIM_FAILED: 2.0,
    ANIM_GREET: 2.4,
    ANIM_CELEBRATE: 1.8,
    ANIM_NOD: 1.2,
    ANIM_STRETCH: 3.4,
    ANIM_RELIEVED: 2.4,
    ANIM_EXHALING: 3.2,
    ANIM_SMOKING: 5.6,
    ANIM_DANCE: 7.2,
}

ONESHOT_ANIMS = frozenset(ONESHOT_S)

SAY_MAX_CHARS = 240
SAY_DEFAULT_S = 6.0

# Hooks we register. Every name is in Hermes VALID_HOOKS (v0.23.0).
HOOK_NAMES: tuple[str, ...] = (
    "pre_tool_call",
    "post_tool_call",
    "pre_llm_call",
    "post_llm_call",
    "on_stream_start",
    "on_stream_delta",
    "on_stream_end",
    "api_request_error",
    "pre_approval_request",
    "post_approval_response",
    "on_human_input_request",
    "on_human_input_resolved",
    "on_session_start",
    "on_session_end",
    "agent_loop_stopped",
    "subagent_start",
    "subagent_stop",
)

_LOCK = threading.RLock()
_STATE: dict[str, Any] = {
    "animation": ANIM_IDLE,
    "until": 0.0,
    "reason": "",
    "costume": DEFAULT_COSTUME,
    "tool_inflight": 0,
    "streaming": False,
    "booting": False,
    "boot_side": "right",
    "awaiting_human": False,
    "vm_crashed": False,
    "hidden": False,
    "enabled_override": None,
}


def _prefs_path() -> Path:
    try:
        from templeos.paths import home as plugin_home

        root = plugin_home()
    except Exception:
        root = Path.home() / ".local" / "share" / "templeos"
    root.mkdir(parents=True, exist_ok=True)
    return root / "companion-prefs.json"


def load_prefs() -> None:
    """Load hide/costume prefs from the plugin data dir (best-effort)."""
    path = _prefs_path()
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(data, dict):
        return
    with _LOCK:
        if "hidden" in data:
            _STATE["hidden"] = bool(data.get("hidden"))
        costume = data.get("costume")
        if isinstance(costume, str) and costume in COSTUMES:
            _STATE["costume"] = costume
        if "enabled" in data:
            raw = data.get("enabled")
            if raw is None:
                _STATE["enabled_override"] = None
            else:
                _STATE["enabled_override"] = bool(raw)


def save_prefs() -> None:
    path = _prefs_path()
    with _LOCK:
        payload = {
            "hidden": bool(_STATE.get("hidden")),
            "costume": _STATE.get("costume") or DEFAULT_COSTUME,
            "enabled": _STATE.get("enabled_override"),
        }
    try:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except Exception:
            pass
    except Exception:
        pass


def set_hidden(hidden: bool) -> bool:
    with _LOCK:
        _STATE["hidden"] = bool(hidden)
    save_prefs()
    return bool(hidden)


def _now() -> float:
    return time.monotonic()


def companion_enabled() -> bool:
    """True unless explicitly turned off via env or a process override."""
    raw = (os.environ.get(ENV_COMPANION) or "").strip().lower()
    if raw in {"0", "false", "no", "off", "none", "disabled"}:
        return False
    if raw in {"1", "true", "yes", "on", "terry"}:
        return True
    # Default: on (tribute). Settings companion=off is applied by set_enabled_override.
    override = _STATE.get("enabled_override")
    if override is False:
        return False
    if override is True:
        return True
    return True


def set_enabled_override(value: bool | None) -> None:
    """Pane/settings can pin enabled on/off; None clears to env/default."""
    with _LOCK:
        _STATE["enabled_override"] = value
    save_prefs()


_OFF_TOKENS = {"0", "false", "no", "off", "none", "disabled"}
_ON_TOKENS = {"1", "true", "yes", "on", "terry"}


def _config_companion_value(ctx: Any) -> Any:
    """Best-effort read of the plugin config ``companion`` setting from ctx."""
    if ctx is None:
        return None
    for attr in ("config", "settings", "plugin_config"):
        try:
            value = getattr(ctx, attr, None)
        except Exception:
            continue
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if not isinstance(value, dict):
            continue
        if "companion" in value:
            return value.get("companion")
        nested = value.get("templeos")
        if isinstance(nested, dict) and "companion" in nested:
            return nested.get("companion")
    for meth in ("get_config", "config_get"):
        fn = getattr(ctx, meth, None)
        if not callable(fn):
            continue
        for key in ("companion", "templeos.companion"):
            try:
                value = fn(key)
            except Exception:
                continue
            if value is not None:
                return value
    return None


def apply_config(ctx: Any) -> bool | None:
    """Apply the plugin's ``companion:`` setting to the process state.

    Returns the resolved enabled flag, or None when the config does not set one.
    Env ``TEMPLEOS_COMPANION`` still wins inside ``companion_enabled()``.
    """
    raw = _config_companion_value(ctx)
    if raw is None:
        return None
    if isinstance(raw, bool):
        resolved = raw
    else:
        token = str(raw).strip().lower()
        if token in _OFF_TOKENS:
            resolved = False
        elif token in _ON_TOKENS:
            resolved = True
        else:
            return None
    # Config is load-time policy, not a user preference: do not persist it.
    with _LOCK:
        _STATE["enabled_override"] = resolved
    return resolved


def reset_state() -> None:
    """Clear companion counters (tests)."""
    with _LOCK:
        _STATE.update(
            {
                "animation": ANIM_IDLE,
                "until": 0.0,
                "reason": "",
                "costume": DEFAULT_COSTUME,
                "tool_inflight": 0,
                "streaming": False,
                "booting": False,
                "boot_side": "right",
                "awaiting_human": False,
                "vm_crashed": False,
                "hidden": False,
                "enabled_override": None,
                "thinking": False,
                "recovering": False,
                "success_flip": False,
                "speech_text": "",
                "speech_until": 0.0,
            }
        )


def set_costume(name: str) -> str:
    costume = str(name or DEFAULT_COSTUME).strip().lower()
    if costume not in COSTUMES:
        costume = DEFAULT_COSTUME
    with _LOCK:
        _STATE["costume"] = costume
    save_prefs()
    return costume


def _pulse(animation: str, *, reason: str = "", hold_s: float | None = None) -> None:
    hold = ONESHOT_S.get(animation, 1.5) if hold_s is None else hold_s
    with _LOCK:
        _STATE["animation"] = animation
        _STATE["until"] = _now() + max(0.1, float(hold))
        _STATE["reason"] = reason


def note_vm_booting(active: bool = True) -> None:
    with _LOCK:
        _STATE["booting"] = bool(active)
        if active:
            _STATE["vm_crashed"] = False
            side = _STATE.get("boot_side") or "right"
            _STATE["boot_side"] = "left" if side == "right" else "right"
            _STATE["reason"] = "vm_booting"


def note_vm_running() -> None:
    with _LOCK:
        _STATE["booting"] = False


def note_vm_crash(reason: str = "vm_crash") -> None:
    with _LOCK:
        _STATE["booting"] = False
        _STATE["vm_crashed"] = True
        _STATE["recovering"] = True
    _pulse(ANIM_FAILED, reason=reason)


def note_user_driving() -> None:
    _pulse(ANIM_WAVING, reason="user_driving")


def _approval_granted(kwargs: dict[str, Any]) -> bool:
    choice = kwargs.get("choice") or kwargs.get("decision") or kwargs.get("approved")
    if isinstance(choice, bool):
        return choice
    token = str(choice or "").strip().lower()
    if token in {"deny", "denied", "reject", "rejected", "no", "false", "0", "block", "cancelled", "canceled"}:
        return False
    # Unknown or empty choice: treat human-input resolved / approval response as granted.
    return True


def say(text: str, *, hold_s: float | None = None) -> dict[str, Any]:
    """Queue a speech bubble. Callers supply the text; nothing is invented."""
    raw = " ".join(str(text or "").split())
    if len(raw) > SAY_MAX_CHARS:
        raw = raw[: SAY_MAX_CHARS - 1].rstrip() + "…"
    hold = SAY_DEFAULT_S if hold_s is None else max(0.8, float(hold_s))
    with _LOCK:
        _STATE["speech_text"] = raw
        _STATE["speech_until"] = (_now() + hold) if raw else 0.0
    return speech_snapshot()


def clear_speech() -> None:
    with _LOCK:
        _STATE["speech_text"] = ""
        _STATE["speech_until"] = 0.0


def speech_snapshot() -> dict[str, Any]:
    with _LOCK:
        text = str(_STATE.get("speech_text") or "")
        until = float(_STATE.get("speech_until") or 0.0)
        if not text or until <= _now():
            if text:
                _STATE["speech_text"] = ""
                _STATE["speech_until"] = 0.0
            return {"text": "", "active": False}
        return {"text": text, "active": True, "remaining_ms": int(max(0, (until - _now()) * 1000))}


def resolve_animation() -> str:
    """Pick the current clip or atlas row from sticky flags + one-shot timers."""
    with _LOCK:
        if not companion_enabled():
            return ANIM_IDLE
        now = _now()
        until = float(_STATE.get("until") or 0.0)
        oneshot = str(_STATE.get("animation") or ANIM_IDLE)
        oneshot_live = until > now and oneshot in ONESHOT_ANIMS

        if _STATE.get("awaiting_human"):
            return ANIM_REVIEW
        if oneshot_live and oneshot == ANIM_FAILED:
            return ANIM_FAILED
        if oneshot_live and oneshot == ANIM_RELIEVED:
            return ANIM_RELIEVED
        # Failed hold just ended: play relieved as the recovery.
        if (not oneshot_live) and oneshot == ANIM_FAILED and _STATE.get("recovering"):
            _STATE["recovering"] = False
            _STATE["vm_crashed"] = False
            hold = ONESHOT_S[ANIM_RELIEVED]
            _STATE["animation"] = ANIM_RELIEVED
            _STATE["until"] = now + hold
            _STATE["reason"] = "recovered"
            return ANIM_RELIEVED
        if oneshot_live and oneshot in {ANIM_CELEBRATE, ANIM_JUMPING}:
            return oneshot
        if _STATE.get("booting"):
            return ANIM_VM_BOOTING
        if int(_STATE.get("tool_inflight") or 0) > 0:
            return ANIM_TYPING
        if _STATE.get("streaming"):
            return ANIM_TALKING
        if _STATE.get("thinking"):
            return ANIM_WAITING
        if oneshot_live:
            return oneshot
        _STATE["animation"] = ANIM_IDLE
        _STATE["reason"] = ""
        if _STATE.get("vm_crashed"):
            _STATE["vm_crashed"] = False
        _STATE["recovering"] = False
        return ANIM_IDLE


def snapshot() -> dict[str, Any]:
    """Shape nested under status_payload()['companion']."""
    anim = resolve_animation()
    with _LOCK:
        speech = speech_snapshot()
        return {
            "enabled": companion_enabled(),
            "hidden": bool(_STATE.get("hidden")),
            "character": "terry",
            "animation": anim,
            "costume": _STATE.get("costume") or DEFAULT_COSTUME,
            "reason": _STATE.get("reason") or "",
            "tribute": True,
            "attribution": (
                "Original fan-made tribute inspired by Terry A. Davis. "
                "No official TempleOS affiliation."
            ),
            "costumes": list(COSTUMES),
            "clips": list(RICH_CLIPS),
            "tool_inflight": int(_STATE.get("tool_inflight") or 0),
            "streaming": bool(_STATE.get("streaming")),
            "thinking": bool(_STATE.get("thinking")),
            "booting": bool(_STATE.get("booting")),
            "awaiting_human": bool(_STATE.get("awaiting_human")),
            "speech": speech,
        }


def _asset_dir(costume: str) -> Path:
    costume = costume if costume in COSTUMES else DEFAULT_COSTUME
    if costume == "base":
        return ASSETS_ROOT
    return ASSETS_ROOT / costume


def atlas_payload(costume: str | None = None) -> dict[str, Any]:
    """Load atlas PNG+JSON as a ctx.rest-safe JSON envelope (base64)."""
    if not companion_enabled():
        return {
            "ok": False,
            "error": "Companion is off.",
            "code": "companion_off",
            "fix": "Set TEMPLEOS_COMPANION=terry or companion: terry to enable.",
        }
    chosen = set_costume(costume or _STATE.get("costume") or DEFAULT_COSTUME)
    folder = _asset_dir(chosen)
    png_path = folder / "atlas.png"
    json_path = folder / "atlas.json"
    if not png_path.is_file() or not json_path.is_file():
        return {
            "ok": False,
            "error": f"Missing Terry atlas for costume {chosen!r}.",
            "code": "companion_asset_missing",
            "fix": "Reinstall the plugin so desktop/assets/companion/terry is present.",
        }
    # Containment: resolved path must stay under ASSETS_ROOT.
    try:
        png_path.resolve().relative_to(ASSETS_ROOT.resolve())
        json_path.resolve().relative_to(ASSETS_ROOT.resolve())
    except ValueError:
        return {
            "ok": False,
            "error": "Companion asset path escaped the asset root.",
            "code": "path_escape",
            "fix": "Report a bug; do not load companion assets from elsewhere.",
        }
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    data = base64.b64encode(png_path.read_bytes()).decode("ascii")
    return {
        "ok": True,
        "error": None,
        "code": None,
        "fix": None,
        "costume": chosen,
        "mime": "image/png",
        "data": data,
        "atlas": meta,
        "bytes": png_path.stat().st_size,
    }


def _clips_dir() -> Path:
    return ASSETS_ROOT / "clips"


def clips_manifest() -> dict[str, Any]:
    """List pre-baked v2 clips (no image payload)."""
    if not companion_enabled():
        return {
            "ok": False,
            "error": "Companion is off.",
            "code": "companion_off",
            "fix": "Set TEMPLEOS_COMPANION=terry or companion: terry to enable.",
        }
    path = _clips_dir() / "manifest.json"
    if not path.is_file():
        return {
            "ok": False,
            "error": "Companion clip manifest is missing.",
            "code": "companion_asset_missing",
            "fix": "Reinstall the plugin so desktop/assets/companion/terry/clips is present.",
        }
    try:
        path.resolve().relative_to(ASSETS_ROOT.resolve())
    except ValueError:
        return {
            "ok": False,
            "error": "Companion asset path escaped the asset root.",
            "code": "path_escape",
            "fix": "Report a bug; do not load companion assets from elsewhere.",
        }
    meta = json.loads(path.read_text(encoding="utf-8"))
    return {"ok": True, "error": None, "code": None, "fix": None, "manifest": meta}


def clip_payload(name: str) -> dict[str, Any]:
    """Load one pre-baked clip strip as a ctx.rest-safe JSON envelope (base64)."""
    if not companion_enabled():
        return {
            "ok": False,
            "error": "Companion is off.",
            "code": "companion_off",
            "fix": "Set TEMPLEOS_COMPANION=terry or companion: terry to enable.",
        }
    token = str(name or "").strip().lower()
    # The v4 rig reuses the existing clip route so the pane needs no new
    # endpoint: v4:bundle returns the part/registry envelope, and
    # v4:<preset> returns one baked high-res clip.
    if token in {"v4", "v4:bundle", "v4-bundle"}:
        return v4_bundle_payload()
    if token.startswith("v4:"):
        return v4_preset_payload(token[3:])
    if token not in RICH_CLIPS:
        return {
            "ok": False,
            "error": f"Unknown companion clip {name!r}.",
            "code": "invalid_args",
            "fix": "Use one of: " + ", ".join(RICH_CLIPS) + ".",
        }
    folder = _clips_dir()
    png_path = folder / f"{token}.png"
    json_path = folder / f"{token}.json"
    if not png_path.is_file() or not json_path.is_file():
        return {
            "ok": False,
            "error": f"Missing Terry clip {token!r}.",
            "code": "companion_asset_missing",
            "fix": "Reinstall the plugin so desktop/assets/companion/terry/clips is present.",
        }
    try:
        png_path.resolve().relative_to(ASSETS_ROOT.resolve())
        json_path.resolve().relative_to(ASSETS_ROOT.resolve())
    except ValueError:
        return {
            "ok": False,
            "error": "Companion asset path escaped the asset root.",
            "code": "path_escape",
            "fix": "Report a bug; do not load companion assets from elsewhere.",
        }
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    data = base64.b64encode(png_path.read_bytes()).decode("ascii")
    return {
        "ok": True,
        "error": None,
        "code": None,
        "fix": None,
        "name": token,
        "mime": "image/png",
        "data": data,
        "clip": meta,
        "bytes": png_path.stat().st_size,
        "costume": "base",
    }


V4_COSTUME_VARIANTS = {
    "base": {},
    "cowboy": {"cap": "cowboy", "torso_overlay": "cowboy_vest"},
    "wizard": {"cap": "wizard", "torso_overlay": "wizard_robe"},
    "chef": {"cap": "chef", "torso_overlay": "chef_apron"},
}


def _v4_path(rel: str) -> Path | None:
    token = str(rel or "").replace("\\", "/").strip()
    if not token or token.startswith("/") or ".." in token.split("/"):
        return None
    try:
        path = (V4_ROOT / token).resolve()
        path.relative_to(V4_ROOT.resolve())
    except (OSError, ValueError):
        return None
    return path


def _v4_json(name: str) -> dict[str, Any]:
    path = _v4_path(name)
    if path is None or not path.is_file():
        raise FileNotFoundError(name)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{name} is not a JSON object")
    return data


@lru_cache(maxsize=1)
def _v4_png_payloads() -> dict[str, str]:
    payloads: dict[str, str] = {}
    for folder in (V4_ROOT / "parts", V4_ROOT / "smoke" / "assets"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.png")):
            rel = path.relative_to(V4_ROOT).as_posix()
            payloads[rel] = base64.b64encode(path.read_bytes()).decode("ascii")
    return payloads


@lru_cache(maxsize=1)
def _v4_baked() -> dict[str, Any]:
    return _v4_json("baked-presets.json")


def clear_v4_cache() -> None:
    _v4_png_payloads.cache_clear()
    _v4_baked.cache_clear()


def v4_bundle_payload() -> dict[str, Any]:
    """Registry, rig, speech and base64 part images for the high-res rig."""
    if not companion_enabled():
        return {
            "ok": False,
            "error": "Companion is off.",
            "code": "companion_off",
            "fix": "Set TEMPLEOS_COMPANION=terry or companion: terry to enable.",
        }
    if not V4_ROOT.is_dir():
        return {
            "ok": False,
            "error": "Missing Terry v4 asset bundle.",
            "code": "companion_asset_missing",
            "fix": "Reinstall the plugin so desktop/assets/companion/terry/v4 is present.",
        }
    try:
        registry = _v4_json("parts.json")
        rig = _v4_json("rig.json")
        speech = _v4_json("speech.json")
        smoke = _v4_json("smoke/smoke.json")
        parts = _v4_png_payloads()
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc) or "Terry v4 bundle is unreadable.",
            "code": "companion_asset_missing",
            "fix": "Reinstall the plugin so desktop/assets/companion/terry/v4 is complete.",
        }
    return {
        "ok": True,
        "error": None,
        "code": None,
        "fix": None,
        "registry": registry,
        "rig": rig,
        "speech": speech,
        "smoke": smoke,
        "costumes": V4_COSTUME_VARIANTS,
        "parts": parts,
        "bytes": sum(len(value) for value in parts.values()),
    }


def v4_preset_payload(name: str) -> dict[str, Any]:
    """One baked clip from baked-presets.json (idle, typing, talking, ...)."""
    if not companion_enabled():
        return {
            "ok": False,
            "error": "Companion is off.",
            "code": "companion_off",
            "fix": "Set TEMPLEOS_COMPANION=terry or companion: terry to enable.",
        }
    token = str(name or "").strip().lower()
    try:
        baked = _v4_baked()
    except Exception:
        return {
            "ok": False,
            "error": "Missing Terry v4 baked presets.",
            "code": "companion_asset_missing",
            "fix": "Reinstall the plugin so desktop/assets/companion/terry/v4 is present.",
        }
    if token not in baked:
        return {
            "ok": False,
            "error": f"Unknown companion preset {name!r}.",
            "code": "invalid_args",
            "fix": "Use one of: " + ", ".join(sorted(baked)) + ".",
        }
    clip = baked[token]
    if not isinstance(clip, dict) or not isinstance(clip.get("frames"), list):
        return {
            "ok": False,
            "error": f"Companion preset {token!r} is malformed.",
            "code": "companion_asset_missing",
            "fix": "Reinstall the plugin so desktop/assets/companion/terry/v4 is complete.",
        }
    return {
        "ok": True,
        "error": None,
        "code": None,
        "fix": None,
        "name": token,
        "clip": clip,
    }


def _tool_ok(kwargs: dict[str, Any]) -> bool:
    """Best-effort success detection for post_tool_call payloads."""
    for key in ("ok", "success"):
        if key in kwargs:
            return bool(kwargs[key])
    result = kwargs.get("result")
    if isinstance(result, dict) and "ok" in result:
        return bool(result.get("ok"))
    if isinstance(result, str):
        try:
            body = json.loads(result)
        except Exception:
            body = None
        if isinstance(body, dict) and "ok" in body:
            return bool(body.get("ok"))
    error = kwargs.get("error")
    if error:
        return False
    status = str(kwargs.get("status") or kwargs.get("outcome") or "").lower()
    if status in {"error", "failed", "failure", "cancelled"}:
        return False
    if status in {"ok", "success", "completed", "done"}:
        return True
    return True


def _make_hooks() -> dict[str, Callable[..., Any]]:
    def on_session_start(**kwargs: Any) -> None:
        _pulse(ANIM_GREET, reason="session_start")

    def on_session_end(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["streaming"] = False
            _STATE["tool_inflight"] = 0
            _STATE["awaiting_human"] = False
            _STATE["booting"] = False
            _STATE["animation"] = ANIM_IDLE
            _STATE["until"] = 0.0
            _STATE["reason"] = "session_end"
            _STATE["thinking"] = False
            _STATE["recovering"] = False
            _STATE["speech_text"] = ""
            _STATE["speech_until"] = 0.0

    def pre_llm_call(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["thinking"] = True
            _STATE["reason"] = "thinking"

    def post_llm_call(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["thinking"] = False

    def on_stream_start(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["streaming"] = True
            _STATE["thinking"] = False
            _STATE["reason"] = "streaming"

    def on_stream_delta(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["streaming"] = True

    def on_stream_end(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["streaming"] = False

    def pre_tool_call(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["tool_inflight"] = int(_STATE.get("tool_inflight") or 0) + 1
            _STATE["reason"] = "tool"

    def post_tool_call(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["tool_inflight"] = max(0, int(_STATE.get("tool_inflight") or 0) - 1)
        if _tool_ok(kwargs):
            with _LOCK:
                _STATE["success_flip"] = not bool(_STATE.get("success_flip"))
                _STATE["recovering"] = False
            _pulse(ANIM_CELEBRATE, reason="tool_ok")
        else:
            with _LOCK:
                _STATE["recovering"] = True
            _pulse(ANIM_FAILED, reason="tool_error")

    def api_request_error(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["recovering"] = True
        _pulse(ANIM_FAILED, reason="api_error")

    def pre_approval_request(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["awaiting_human"] = True
            _STATE["reason"] = "approval"

    def post_approval_response(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["awaiting_human"] = False
        if _approval_granted(kwargs):
            _pulse(ANIM_NOD, reason="approval_granted")

    def on_human_input_request(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["awaiting_human"] = True
            _STATE["reason"] = "human_input"

    def on_human_input_resolved(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["awaiting_human"] = False
        _pulse(ANIM_NOD, reason="human_input_received")

    def agent_loop_stopped(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["streaming"] = False
            _STATE["thinking"] = False
            _STATE["tool_inflight"] = 0
            _STATE["awaiting_human"] = False
        _pulse(ANIM_WAVING, reason="loop_stopped", hold_s=1.2)

    def subagent_start(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["tool_inflight"] = int(_STATE.get("tool_inflight") or 0) + 1
            _STATE["reason"] = "subagent"

    def subagent_stop(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["tool_inflight"] = max(0, int(_STATE.get("tool_inflight") or 0) - 1)
        with _LOCK:
            _STATE["success_flip"] = not bool(_STATE.get("success_flip"))
        _pulse(ANIM_CELEBRATE, reason="subagent_done")

    return {
        "on_session_start": on_session_start,
        "on_session_end": on_session_end,
        "pre_llm_call": pre_llm_call,
        "post_llm_call": post_llm_call,
        "on_stream_start": on_stream_start,
        "on_stream_delta": on_stream_delta,
        "on_stream_end": on_stream_end,
        "pre_tool_call": pre_tool_call,
        "post_tool_call": post_tool_call,
        "api_request_error": api_request_error,
        "pre_approval_request": pre_approval_request,
        "post_approval_response": post_approval_response,
        "on_human_input_request": on_human_input_request,
        "on_human_input_resolved": on_human_input_resolved,
        "agent_loop_stopped": agent_loop_stopped,
        "subagent_start": subagent_start,
        "subagent_stop": subagent_stop,
    }


def register_hooks(ctx: Any) -> list[str]:
    """Register observer hooks on a Hermes PluginContext. Returns names registered.

    Hooks are always registered so a runtime off switch can take effect without
    a reload. Callbacks no-op while companion_enabled() is false.
    """
    if not hasattr(ctx, "register_hook"):
        return []
    # Restore the pane's Hide Terry / costume choice, then let explicit config
    # (and later the env switch inside companion_enabled) override it.
    load_prefs()
    apply_config(ctx)
    registered: list[str] = []
    for name, fn in _make_hooks().items():
        assert name in HOOK_NAMES

        def _safe(cb: Callable[..., Any] = fn, **kwargs: Any) -> None:
            if not companion_enabled():
                return
            try:
                cb(**kwargs)
            except Exception:
                pass

        try:
            ctx.register_hook(name, _safe)
            registered.append(name)
        except Exception:
            continue
    return registered
