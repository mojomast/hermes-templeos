"""Background pane-frame cache so /frame never starves the Hermes gateway.

The Desktop pane used to call look() on every poll (~12 fps). look() does a
QMP screendump, PNG encode, AND full-frame glyph OCR (~0.4–0.8 s each on this
host). That blocked the gateway event loop and QMP, so chat and /input timed
out. This module:

* captures on a daemon thread at a capped rate (≤5 fps, slower when idle)
* skips OCR on the pane path (caption is best-effort / previous)
* serves /frame from the latest cached PNG (unchanged replies are free)
* never holds the arbiter lock
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from typing import Any, Callable

from templeos.tools import CODE_FIX, Code

# Pane budget: at most 5 fps when the guest is changing; back off when idle.
MIN_INTERVAL_S = 0.20
IDLE_INTERVAL_S = 1.0
STOPPED_INTERVAL_S = 1.5
MAX_INTERVAL_S = 2.5
# How long a cached frame stays "fresh" enough to skip a synchronous catch-up.
FRESH_S = 0.35


class FrameCache:
    def __init__(
        self,
        *,
        capture: Callable[[], dict[str, Any]] | None = None,
        vm_running: Callable[[], bool] | None = None,
        min_interval_s: float = MIN_INTERVAL_S,
        idle_interval_s: float = IDLE_INTERVAL_S,
    ) -> None:
        self._capture = capture or _default_capture
        self._vm_running = vm_running or _default_vm_running
        self._min_interval_s = float(min_interval_s)
        self._idle_interval_s = float(idle_interval_s)
        self._lock = threading.RLock()
        self._latest: dict[str, Any] | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._interval_s = self._min_interval_s
        self._last_capture_at = 0.0
        self._unchanged_streak = 0
        self._captures = 0
        self._errors = 0

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="templeos-frame-cache",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        with self._lock:
            self._thread = None

    def reset(self) -> None:
        """Drop the cached frame (tests / VM stop)."""
        with self._lock:
            self._latest = None
            self._unchanged_streak = 0
            self._interval_s = self._min_interval_s

    def poke(self) -> None:
        """Ask for a sooner refresh after user or agent input."""
        with self._lock:
            self._interval_s = self._min_interval_s
            self._unchanged_streak = 0
        self._wake.set()
        self.start()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._thread is not None and self._thread.is_alive(),
                "interval_s": self._interval_s,
                "captures": self._captures,
                "errors": self._errors,
                "has_frame": self._latest is not None,
                "sha256": (self._latest or {}).get("sha256"),
                "age_s": (
                    round(time.monotonic() - float((self._latest or {}).get("_ts") or 0.0), 4)
                    if self._latest
                    else None
                ),
            }

    def get(self, *, since: str | None = None, allow_sync: bool = True) -> dict[str, Any]:
        """Return the latest pane frame. Never runs OCR. Rarely blocks.

        When ``since`` matches the cached sha256, returns ``unchanged: true``
        with no payload. On a cold cache, optionally does one synchronous
        capture so unit tests and the first paint still work.
        """
        self.start()
        tag = (since or "").strip().strip('"')
        with self._lock:
            latest = dict(self._latest) if self._latest else None
        if latest is not None:
            sha = str(latest.get("sha256") or "")
            if tag and sha and tag == sha:
                return _unchanged(latest)
            age = time.monotonic() - float(latest.get("_ts") or 0.0)
            if age <= max(FRESH_S, self._min_interval_s * 2) or not allow_sync:
                return _public(latest)
        if not allow_sync:
            if latest is not None:
                return _public(latest)
            return _stopped()
        # Cold cache or stale: one sync capture, then return.
        body = self._capture_once()
        if tag and body.get("ok") and body.get("sha256") and tag == str(body["sha256"]):
            return _unchanged(body)
        return _public(body)

    def _run(self) -> None:
        while not self._stop.is_set():
            running = False
            try:
                running = bool(self._vm_running())
            except Exception:
                running = False
            if running:
                self._capture_once()
            else:
                with self._lock:
                    if self._latest is not None and self._latest.get("code") != Code.VM_NOT_RUNNING:
                        # Keep last good frame briefly; mark stopped on next get via age.
                        pass
                self._interval_s = STOPPED_INTERVAL_S
            self._wake.clear()
            self._wake.wait(timeout=self._interval_s)

    def _capture_once(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            raw = self._capture()
        except Exception as exc:
            with self._lock:
                self._errors += 1
            body = {
                "ok": False,
                "error": f"Frame capture failed: {exc}",
                "code": "internal_error",
                "fix": CODE_FIX.get("internal_error", "See docs/CONTRACTS.md."),
                "mime": "image/png",
                "data": None,
                "unchanged": False,
                "_ts": time.monotonic(),
                "_capture_ms": round((time.monotonic() - started) * 1000.0, 2),
            }
            with self._lock:
                self._latest = body
            return body
        if not isinstance(raw, dict):
            raw = {
                "ok": False,
                "error": "capture returned a non-object",
                "code": "internal_error",
                "mime": "image/png",
                "data": None,
            }
        body = dict(raw)
        body.setdefault("ok", True)
        body.setdefault("mime", "image/png")
        body.setdefault("data", None)
        body["unchanged"] = False
        body["_ts"] = time.monotonic()
        body["_capture_ms"] = round((time.monotonic() - started) * 1000.0, 2)
        with self._lock:
            prev = self._latest
            self._captures += 1
            self._last_capture_at = body["_ts"]
            if (
                prev
                and prev.get("ok")
                and body.get("ok")
                and prev.get("sha256")
                and prev.get("sha256") == body.get("sha256")
            ):
                self._unchanged_streak += 1
                # Keep previous base64 if the new capture omitted it.
                if not body.get("data") and prev.get("data"):
                    body["data"] = prev["data"]
            else:
                self._unchanged_streak = 0
            if self._unchanged_streak >= 2:
                self._interval_s = min(MAX_INTERVAL_S, self._idle_interval_s)
            else:
                self._interval_s = self._min_interval_s
            # Adaptive: if a capture was slow, back off so we never spin the gateway.
            capture_ms = float(body.get("_capture_ms") or 0.0)
            if capture_ms > 250:
                self._interval_s = max(self._interval_s, min(MAX_INTERVAL_S, capture_ms / 1000.0 * 2))
            self._latest = body
        return body


_CACHE: FrameCache | None = None
_CACHE_LOCK = threading.Lock()


def get_frame_cache() -> FrameCache:
    global _CACHE
    with _CACHE_LOCK:
        if _CACHE is None:
            _CACHE = FrameCache()
        return _CACHE


def reset_frame_cache() -> FrameCache:
    global _CACHE
    with _CACHE_LOCK:
        if _CACHE is not None:
            _CACHE.stop()
            _CACHE.reset()
        _CACHE = FrameCache()
        return _CACHE


def _default_vm_running() -> bool:
    try:
        from templeos import vm as vm_mod
    except Exception:
        return False
    getter = getattr(vm_mod, "get_runtime", None)
    if not callable(getter):
        return False
    try:
        return getter() is not None
    except Exception:
        return False


def _default_capture() -> dict[str, Any]:
    """Pane capture: screendump + PNG + crop hash. No glyph OCR."""
    from templeos.screen import (
        ScreenError,
        capture_image,
        encode_png,
        hash_image,
        require_runtime,
    )

    try:
        rt = require_runtime()
        im = capture_image()
        data, out = encode_png(im)
        encoded = base64.b64encode(data).decode("ascii")
        sha = hashlib.sha256(data).hexdigest()
        try:
            crop_info = hash_image(im, flavor=rt.flavor)
        except Exception:
            crop_info = {}
        return {
            "ok": True,
            "mime": "image/png",
            "width": out.width,
            "height": out.height,
            "data": encoded,
            "sha256": sha,
            "caption": f"{out.width}x{out.height} PNG",
            "crop_sha256": crop_info.get("sha256"),
            "text_confidence": None,
        }
    except ScreenError as exc:
        return dict(exc.envelope)
    except NotImplementedError as exc:
        return {
            "ok": False,
            "error": str(exc) or "Frame capture is not implemented yet.",
            "code": Code.NOT_IMPLEMENTED,
            "fix": CODE_FIX.get(Code.NOT_IMPLEMENTED, "See docs/CONTRACTS.md."),
            "mime": "image/png",
            "data": None,
        }


def _public(body: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in body.items() if not str(k).startswith("_")}
    out.setdefault("unchanged", False)
    return out


def _unchanged(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "error": None,
        "code": None,
        "fix": None,
        "mime": body.get("mime") or "image/png",
        "data": None,
        "width": body.get("width"),
        "height": body.get("height"),
        "sha256": body.get("sha256"),
        "caption": body.get("caption"),
        "unchanged": True,
    }


def _stopped() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "The TempleOS VM is not running.",
        "code": Code.VM_NOT_RUNNING,
        "fix": CODE_FIX.get(Code.VM_NOT_RUNNING, "Call templeos_vm op=start, then retry."),
        "mime": "image/png",
        "data": None,
        "unchanged": False,
    }


def frame_from_cache(*, since: str | None = None, allow_sync: bool = True) -> dict[str, Any]:
    return get_frame_cache().get(since=since, allow_sync=allow_sync)


# Silence unused import warning for json in type checkers; kept for future debug dumps.
_ = json
