"""Input arbitration: watch, shared, or user, with a single queue.

Modes:
  watch  — the user sees the VM; only the agent injects input.
  shared — both can type (default). User key/click starts a hold-off
           (USER_HOLD_OFF_S, about two seconds) during which agent tools
           return agent_paused.
  user   — Take control. Agent tools return agent_paused until Hand back.

One lock serializes user events and tool calls so they never interleave
inside QEMU.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

MODES = ("watch", "shared", "user")
DEFAULT_MODE = "shared"
USER_HOLD_OFF_S = 2.0
CODE_AGENT_PAUSED = "agent_paused"

_PAUSED_ERROR = "Agent input is paused because the user is driving the VM."
_PAUSED_FIX = "Wait for the hold-off to end, or ask the user to click Hand back."


class Arbiter:
    def __init__(self, hold_off_s: float = USER_HOLD_OFF_S) -> None:
        if hold_off_s < 0:
            raise ValueError("hold_off_s must be >= 0")
        self.hold_off_s = float(hold_off_s)
        self.mode = DEFAULT_MODE
        self._lock = threading.RLock()
        self._user_until = 0.0

    @contextmanager
    def queue(self) -> Iterator["Arbiter"]:
        """The single serialization point for user events and agent tools."""
        with self._lock:
            yield self

    def set_mode(self, mode: str) -> dict[str, Any]:
        with self._lock:
            if mode not in MODES:
                raise ValueError(f"mode must be one of {', '.join(MODES)}, not {mode!r}")
            self.mode = mode
            if mode != "shared":
                self._user_until = 0.0
            return self.snapshot()

    def take_control(self) -> dict[str, Any]:
        return self.set_mode("user")

    def hand_back(self) -> dict[str, Any]:
        return self.set_mode("shared")

    def note_user_input(self, *, now: float | None = None) -> dict[str, Any]:
        """Record a user key or click. In shared mode this starts the hold-off."""
        with self._lock:
            clock = time.monotonic() if now is None else now
            if self.mode == "shared":
                self._user_until = clock + self.hold_off_s
            return self.snapshot(now=clock)

    def remaining_hold_off(self, *, now: float | None = None) -> float:
        clock = time.monotonic() if now is None else now
        return max(0.0, self._user_until - clock)

    def agent_paused(self, *, now: float | None = None) -> bool:
        with self._lock:
            if self.mode == "user":
                return True
            if self.mode == "watch":
                return False
            return self.remaining_hold_off(now=now) > 0

    def user_may_input(self) -> bool:
        """False in watch mode: the pane should not inject user events."""
        with self._lock:
            return self.mode != "watch"

    def agent_may_input(self, *, now: float | None = None) -> tuple[bool, dict[str, Any] | None]:
        """Return (allowed, paused_envelope_or_None). Call inside queue()."""
        with self._lock:
            if not self.agent_paused(now=now):
                return True, None
            return False, self.paused_envelope(now=now)

    def paused_envelope(self, *, now: float | None = None) -> dict[str, Any]:
        remaining = self.remaining_hold_off(now=now)
        return {
            "ok": False,
            "error": _PAUSED_ERROR,
            "code": CODE_AGENT_PAUSED,
            "fix": _PAUSED_FIX,
            "mode": self.mode,
            "hold_off_s": remaining if self.mode == "shared" else 0.0,
        }

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        clock = time.monotonic() if now is None else now
        remaining = self.remaining_hold_off(now=clock)
        paused = self.mode == "user" or (self.mode == "shared" and remaining > 0)
        return {
            "mode": self.mode,
            "agent_paused": paused,
            "hold_off_s": remaining if self.mode == "shared" else 0.0,
            "user_may_input": self.mode != "watch",
        }


_CURRENT: Arbiter | None = None
_CURRENT_LOCK = threading.Lock()


def get_arbiter() -> Arbiter:
    global _CURRENT
    with _CURRENT_LOCK:
        if _CURRENT is None:
            _CURRENT = Arbiter()
        return _CURRENT


def reset_arbiter(arbiter: Arbiter | None = None) -> Arbiter:
    """Replace the process-wide arbiter (tests)."""
    global _CURRENT
    with _CURRENT_LOCK:
        _CURRENT = arbiter if arbiter is not None else Arbiter()
        return _CURRENT
