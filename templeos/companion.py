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
import threading
import time
from pathlib import Path
from typing import Any, Callable

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = PLUGIN_ROOT / "desktop" / "assets" / "companion" / "terry"

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

ONESHOT_S = {
    ANIM_WAVING: 2.2,
    ANIM_JUMPING: 1.3,
    ANIM_FAILED: 2.0,
}

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
    _pulse(ANIM_FAILED, reason=reason)


def note_user_driving() -> None:
    _pulse(ANIM_WAVING, reason="user_driving")


def resolve_animation() -> str:
    """Pick the current atlas row from sticky flags + one-shot timers."""
    with _LOCK:
        if not companion_enabled():
            return ANIM_IDLE
        now = _now()
        until = float(_STATE.get("until") or 0.0)
        oneshot = str(_STATE.get("animation") or ANIM_IDLE)
        oneshot_live = until > now and oneshot in {ANIM_WAVING, ANIM_JUMPING, ANIM_FAILED}

        if _STATE.get("awaiting_human"):
            return ANIM_REVIEW
        if _STATE.get("vm_crashed") and oneshot_live and oneshot == ANIM_FAILED:
            return ANIM_FAILED
        if oneshot_live and oneshot == ANIM_FAILED:
            return ANIM_FAILED
        if oneshot_live and oneshot == ANIM_JUMPING:
            return ANIM_JUMPING
        if _STATE.get("booting"):
            return ANIM_RUNNING_RIGHT if _STATE.get("boot_side") == "right" else ANIM_RUNNING_LEFT
        if int(_STATE.get("tool_inflight") or 0) > 0:
            return ANIM_RUNNING
        if _STATE.get("streaming"):
            return ANIM_WAITING
        if oneshot_live and oneshot == ANIM_WAVING:
            return ANIM_WAVING
        if until <= now:
            _STATE["animation"] = ANIM_IDLE
            _STATE["reason"] = ""
            if _STATE.get("vm_crashed"):
                _STATE["vm_crashed"] = False
        return ANIM_IDLE


def snapshot() -> dict[str, Any]:
    """Shape nested under status_payload()['companion']."""
    anim = resolve_animation()
    with _LOCK:
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
            "tool_inflight": int(_STATE.get("tool_inflight") or 0),
            "streaming": bool(_STATE.get("streaming")),
            "booting": bool(_STATE.get("booting")),
            "awaiting_human": bool(_STATE.get("awaiting_human")),
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
        _pulse(ANIM_WAVING, reason="session_start")

    def on_session_end(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["streaming"] = False
            _STATE["tool_inflight"] = 0
            _STATE["awaiting_human"] = False
            _STATE["booting"] = False
            _STATE["animation"] = ANIM_IDLE
            _STATE["until"] = 0.0
            _STATE["reason"] = "session_end"

    def pre_llm_call(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["streaming"] = True
            _STATE["reason"] = "thinking"

    def post_llm_call(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["streaming"] = False

    def on_stream_start(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["streaming"] = True
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
            _pulse(ANIM_JUMPING, reason="tool_ok")
        else:
            _pulse(ANIM_FAILED, reason="tool_error")

    def api_request_error(**kwargs: Any) -> None:
        _pulse(ANIM_FAILED, reason="api_error")

    def pre_approval_request(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["awaiting_human"] = True
            _STATE["reason"] = "approval"

    def post_approval_response(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["awaiting_human"] = False

    def on_human_input_request(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["awaiting_human"] = True
            _STATE["reason"] = "human_input"

    def on_human_input_resolved(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["awaiting_human"] = False

    def agent_loop_stopped(**kwargs: Any) -> None:
        with _LOCK:
            _STATE["streaming"] = False
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
        _pulse(ANIM_JUMPING, reason="subagent_done", hold_s=1.0)

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
