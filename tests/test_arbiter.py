from __future__ import annotations

import time

import pytest

from templeos.arbiter import USER_HOLD_OFF_S, Arbiter, get_arbiter, reset_arbiter


def test_default_is_shared_and_agent_may_input(tos_home):
    arb = reset_arbiter()
    assert arb.mode == "shared"
    assert USER_HOLD_OFF_S == 2.0
    allowed, paused = arb.agent_may_input()
    assert allowed is True and paused is None


def test_user_mode_pauses_agent():
    arb = Arbiter()
    arb.take_control()
    allowed, paused = arb.agent_may_input()
    assert allowed is False
    assert paused["code"] == "agent_paused"
    assert paused["ok"] is False
    assert paused["mode"] == "user"
    snap = arb.hand_back()
    assert snap["mode"] == "shared"
    assert arb.agent_may_input()[0] is True


def test_watch_blocks_user_but_not_agent():
    arb = Arbiter()
    arb.set_mode("watch")
    assert arb.user_may_input() is False
    assert arb.agent_may_input()[0] is True
    with pytest.raises(ValueError):
        arb.set_mode("god")


def test_shared_hold_off(monkeypatch):
    arb = Arbiter(hold_off_s=2.0)
    now = 1000.0
    arb.note_user_input(now=now)
    allowed, paused = arb.agent_may_input(now=now + 0.5)
    assert allowed is False and paused["code"] == "agent_paused"
    assert paused["hold_off_s"] == pytest.approx(1.5)
    assert arb.agent_may_input(now=now + 2.0)[0] is True


def test_queue_serializes(tos_home):
    arb = get_arbiter()
    with arb.queue() as held:
        held.note_user_input()
        assert held.agent_paused() is True
