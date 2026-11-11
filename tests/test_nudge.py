from __future__ import annotations

from templeos import companion, nudge
from tests.fakes import FakeCtx


def setup_function(_fn=None):
    nudge.reset_state()
    companion.reset_state()


def test_quiet_when_nothing_pending(tos_home, monkeypatch):
    monkeypatch.delenv("TEMPLEOS_NUDGE", raising=False)
    assert nudge.pre_llm_call() is None


def test_one_line_and_two_per_day_cap(tos_home, monkeypatch):
    monkeypatch.delenv("TEMPLEOS_NUDGE", raising=False)
    nudge.record_pending(bbs_replies=2, project="Hermes", next_step="wire nudge")
    first = nudge.pre_llm_call()
    second = nudge.pre_llm_call()
    third = nudge.pre_llm_call()
    assert first == "2 BBS replies waiting; project Hermes next step: wire nudge"
    assert second == first
    assert third is None
    assert nudge.load_state()["fired"] == nudge.MAX_PER_DAY


def test_singular_reply_and_mail(tos_home, monkeypatch):
    monkeypatch.delenv("TEMPLEOS_NUDGE", raising=False)
    nudge.record_pending(bbs_replies=1, bbs_mail=1)
    assert nudge.pre_llm_call() == "1 BBS reply waiting; 1 BBS mail waiting"


def test_env_off_disables_completely(tos_home, monkeypatch):
    nudge.record_pending(bbs_replies=4, next_step="rest")
    monkeypatch.setenv("TEMPLEOS_NUDGE", "off")
    assert nudge.pre_llm_call() is None
    assert nudge.load_state()["fired"] == 0


def test_config_off_disables(tos_home, monkeypatch):
    monkeypatch.delenv("TEMPLEOS_NUDGE", raising=False)
    nudge.record_pending(bbs_replies=4)
    ctx = FakeCtx()
    ctx.config = {"nudge": "off"}
    assert nudge.pre_llm_call(ctx=ctx) is None


def test_registration_composes_with_companion_hook(tos_home, monkeypatch):
    monkeypatch.delenv("TEMPLEOS_NUDGE", raising=False)
    companion.reset_state()
    ctx = FakeCtx()
    companion.register_hooks(ctx)
    registered = nudge.register_hooks(ctx)
    assert registered == ["pre_llm_call"]
    assert nudge.register_hooks(ctx) == []
    nudge.record_pending(bbs_replies=2, project="X", next_step="Y")
    line = ctx.hooks["pre_llm_call"]()
    assert line == "2 BBS replies waiting; project X next step: Y"
    assert companion.snapshot()["thinking"] is True


def test_registration_works_through_plugin_config(tos_home, monkeypatch):
    monkeypatch.delenv("TEMPLEOS_NUDGE", raising=False)
    from templeos.settings import apply_config

    ctx = FakeCtx()
    companion.register_hooks(ctx)
    apply_config(ctx)
    nudge.record_pending(next_step="finish slice")
    assert ctx.hooks["pre_llm_call"]() == "next step: finish slice"
