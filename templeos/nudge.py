"""Pending-only, rate-limited context nudge for the four TempleOS tools.

The nudge is persisted in the plugin data dir and never stores credentials,
screen pixels, or post bodies. It fires at most twice per local day and only
when session/digest helpers recorded something pending.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Any, Callable

from templeos.paths import home
from templeos.settings import DEFAULT_NUDGE, ENV_NUDGE, nudge_enabled

STATE_NAME = "nudge.json"
MAX_PER_DAY = 2
MAX_ITEM_CHARS = 60
_WHITESPACE = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MODE = 0o600


def _state_path() -> Path:
    return home() / STATE_NAME


def _today() -> str:
    return _dt.date.today().isoformat()


def _clean(value: Any, limit: int = MAX_ITEM_CHARS) -> str:
    text = _CONTROL.sub(" ", str(value or ""))
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:limit]


def empty_state() -> dict[str, Any]:
    return {"date": _today(), "fired": 0, "pending": {}}


def load_state() -> dict[str, Any]:
    path = _state_path()
    state = empty_state()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            raw = None
        if isinstance(raw, dict):
            pending = raw.get("pending")
            if isinstance(pending, dict):
                state["pending"] = pending
            try:
                state["fired"] = max(0, int(raw.get("fired") or 0))
            except (TypeError, ValueError):
                state["fired"] = 0
            if isinstance(raw.get("date"), str):
                state["date"] = raw["date"]
    if state["date"] != _today():
        state["date"] = _today()
        state["fired"] = 0
    return state


def save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "date": str(state.get("date") or _today()),
        "fired": max(0, int(state.get("fired") or 0)),
        "pending": state.get("pending") if isinstance(state.get("pending"), dict) else {},
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(_MODE)
    except OSError:
        pass


def reset_state() -> None:
    try:
        _state_path().unlink()
    except OSError:
        pass


def record_pending(
    *,
    bbs_replies: int | None = None,
    bbs_mail: int | None = None,
    project: str | None = None,
    next_step: str | None = None,
) -> dict[str, Any]:
    """Store the latest compact hints without ever storing message bodies."""
    state = load_state()
    pending = dict(state.get("pending") or {})
    if bbs_replies is not None:
        pending["bbs_replies"] = max(0, int(bbs_replies))
    if bbs_mail is not None:
        pending["bbs_mail"] = max(0, int(bbs_mail))
    if project is not None:
        pending["project"] = _clean(project)
    if next_step is not None:
        pending["next_step"] = _clean(next_step, 80)
    state["pending"] = {k: v for k, v in pending.items() if v not in (None, "", 0)}
    save_state(state)
    return state


def pending_line(state: dict[str, Any] | None = None) -> str | None:
    state = load_state() if state is None else state
    pending = state.get("pending") if isinstance(state.get("pending"), dict) else {}
    parts: list[str] = []
    replies = int(pending.get("bbs_replies") or 0)
    mail = int(pending.get("bbs_mail") or 0)
    if replies:
        parts.append(f"{replies} BBS repl{'y' if replies == 1 else 'ies'} waiting")
    if mail:
        parts.append(f"{mail} BBS mail waiting")
    project = _clean(pending.get("project"))
    next_step = _clean(pending.get("next_step"), 80)
    if next_step:
        if project:
            parts.append(f"project {project} next step: {next_step}")
        else:
            parts.append(f"next step: {next_step}")
    if not parts:
        return None
    return _clean("; ".join(parts), 240)


def pre_llm_call(ctx: Any = None, **_: Any) -> str | None:
    """Return at most one short context line, or None when quiet/disabled."""
    if not nudge_enabled(ctx):
        return None
    state = load_state()
    line = pending_line(state)
    if line is None:
        return None
    if int(state.get("fired") or 0) >= MAX_PER_DAY:
        return None
    state["fired"] = int(state.get("fired") or 0) + 1
    state["date"] = _today()
    save_state(state)
    return line


def register_hooks(ctx: Any) -> list[str]:
    if not hasattr(ctx, "register_hook"):
        return []
    if getattr(ctx, "_templeos_nudge_registered", False):
        return []
    try:
        setattr(ctx, "_templeos_nudge_registered", True)
    except Exception:
        pass

    existing: Callable[..., Any] | None = None
    hooks = getattr(ctx, "hooks", None)
    if isinstance(hooks, dict):
        candidate = hooks.get("pre_llm_call")
        if callable(candidate):
            existing = candidate

    def _safe(**kwargs: Any) -> Any:
        prior = None
        if existing is not None:
            try:
                prior = existing(**kwargs)
            except Exception:
                prior = None
        try:
            line = pre_llm_call(ctx=ctx, **kwargs)
        except Exception:
            line = None
        if line and isinstance(prior, str) and prior:
            return f"{prior}\n{line}"
        return line or prior

    try:
        ctx.register_hook("pre_llm_call", _safe)
    except Exception:
        return []
    return ["pre_llm_call"]
