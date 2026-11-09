"""Frame cache keeps /frame off the look()/OCR path so the gateway stays responsive."""

from __future__ import annotations

import json
import threading
import time

import pytest

from templeos.api import frame_payload, user_input, set_control, reset_activity_log
from templeos.arbiter import reset_arbiter
from templeos.frame_cache import FrameCache, reset_frame_cache


@pytest.fixture
def fresh(tos_home):
    reset_arbiter()
    reset_activity_log()
    reset_frame_cache()
    return tos_home


def test_unchanged_frame_is_free_and_skips_capture(fresh):
    calls = {"n": 0}

    def capture():
        calls["n"] += 1
        time.sleep(0.05)  # pretend a screendump costs something
        return {
            "ok": True,
            "mime": "image/png",
            "data": "AAAA",
            "width": 640,
            "height": 480,
            "sha256": "ab" * 32,
            "caption": "cached",
        }

    cache = FrameCache(capture=capture, vm_running=lambda: True, min_interval_s=0.2)
    try:
        first = cache.get(allow_sync=True)
        assert first["ok"] is True
        assert first["unchanged"] is False
        assert calls["n"] >= 1
        n_before = calls["n"]
        cheap = cache.get(since=first["sha256"], allow_sync=False)
        assert cheap["unchanged"] is True
        assert cheap["data"] is None
        assert calls["n"] == n_before  # unchanged path must not capture again
    finally:
        cache.stop()


def test_frame_payload_budget_under_load(fresh, monkeypatch):
    """100 cached polls must stay well under a second and never call look()."""
    looks = {"n": 0}

    def boom_look():
        looks["n"] += 1
        time.sleep(0.4)  # old path cost
        return {
            "ok": True,
            "mime": "image/png",
            "data": "BBBB",
            "width": 640,
            "height": 480,
            "sha256": "cd" * 32,
            "caption": "slow",
        }

    monkeypatch.setattr("templeos.screen.look", boom_look)
    # Seed via the monkeypatched look once (test seam), then pound since=.
    first = frame_payload()
    assert first["ok"] is True
    assert looks["n"] == 1
    sha = first["sha256"]
    started = time.perf_counter()
    for _ in range(100):
        body = frame_payload(since=sha)
        assert body["unchanged"] is True
        assert body["data"] is None
    elapsed = time.perf_counter() - started
    assert looks["n"] == 1, "unchanged polls must not call look()/OCR"
    assert elapsed < 0.5, f"100 unchanged /frame polls took {elapsed:.3f}s"


def test_background_capture_does_not_block_get(fresh):
    gate = threading.Event()
    started = threading.Event()

    def capture():
        started.set()
        gate.wait(timeout=2.0)
        return {
            "ok": True,
            "mime": "image/png",
            "data": "CCCC",
            "width": 64,
            "height": 48,
            "sha256": "ef" * 32,
            "caption": "bg",
        }

    cache = FrameCache(capture=capture, vm_running=lambda: True, min_interval_s=0.05)
    try:
        # Seed a frame, then let the background thread block inside capture.
        with cache._lock:
            cache._latest = {
                "ok": True,
                "mime": "image/png",
                "data": "SEED",
                "width": 64,
                "height": 48,
                "sha256": "aa" * 32,
                "caption": "seed",
                "_ts": time.monotonic(),
            }
        cache.start()
        # Wait until background capture is in flight, then get() must still return fast.
        assert started.wait(timeout=2.0)
        t0 = time.perf_counter()
        body = cache.get(allow_sync=False)
        took = time.perf_counter() - t0
        assert body["sha256"] == "aa" * 32
        assert took < 0.05
    finally:
        gate.set()
        cache.stop()


def test_user_input_pokes_cache_and_returns_fast(fresh, monkeypatch):
    seen = {}

    def type_text(text, delay_s=0.0):
        seen["text"] = text
        seen["delay_s"] = delay_s
        return {"ok": True, "typed": len(text)}

    monkeypatch.setattr("templeos.input.type_text", type_text)
    set_control({"op": "handback"})
    t0 = time.perf_counter()
    body = user_input({"type": "type", "text": "n"})
    took = time.perf_counter() - t0
    assert body["ok"] is True
    assert seen["text"] == "n"
    assert seen["delay_s"] == 0.0
    assert took < 0.2
