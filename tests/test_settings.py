from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from templeos.flavors import DEFAULT, get_flavor
from templeos.settings import (
    apply_config,
    apply_flavor_choice,
    flavor_status,
    iso_state,
    load_preferred,
    save_preferred,
)
from templeos.tools import handle_vm
from templeos.api import settings_payload, status_payload


def _parse(raw: str) -> dict:
    return json.loads(raw)


def test_default_preferred_is_templeoh(tos_home):
    assert DEFAULT == "templeoh"
    assert load_preferred() == "templeoh"
    rec = get_flavor("temple-of-hermes")
    assert rec["id"] == "templeoh"
    assert rec["sha256"] == "fbaa3d6f0a8f9190f295e933c32cb833a61b3cb43a708309acb6c98ff51ac4fd"
    assert rec["bytes"] == 14_053_376


def test_settings_persist_and_iso_state(tos_home, monkeypatch):
    rec = get_flavor("tinkeros")
    payload = b"tinker-iso"
    digest = hashlib.sha256(payload).hexdigest()
    from templeos import flavors

    monkeypatch.setitem(flavors.FLAVORS["tinkeros"], "sha256", digest)
    monkeypatch.setitem(flavors.FLAVORS["tinkeros"], "bytes", len(payload))
    dest = tos_home / "isos" / rec["iso_filename"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)

    saved = save_preferred("tinkeros")
    assert saved["id"] == "tinkeros"
    assert load_preferred() == "tinkeros"
    data = json.loads((tos_home / "settings.json").read_text())
    assert data["flavor"] == "tinkeros"
    state = iso_state("tinkeros")
    assert state["sha_state"] == "verified"
    assert state["present"] is True
    assert iso_state("templeoh")["sha_state"] == "missing"


def test_apply_flavor_choice_fetches_and_notices_next_boot(tos_home, monkeypatch):
    rec = get_flavor("templeos")
    payload = b"stock-iso"
    digest = hashlib.sha256(payload).hexdigest()
    from templeos import flavors, doctor

    monkeypatch.setitem(flavors.FLAVORS["templeos"], "sha256", digest)
    monkeypatch.setitem(flavors.FLAVORS["templeos"], "bytes", len(payload))
    seen: dict = {}

    def fake_download(url, dest, *, expected_sha256, expected_bytes=None):
        seen["url"] = url
        Path(dest).write_bytes(payload)
        return Path(dest)

    monkeypatch.setattr(doctor, "download_official", fake_download)
    monkeypatch.setattr("templeos.vm.status", lambda: {"ok": True, "running": True, "flavor": "templeoh"})

    result = apply_flavor_choice("templeos", fetch=True)
    assert result["ok"] is True
    assert result["preferred_flavor"] == "templeos"
    assert result["apply_on_next_boot"] is True
    assert "next boot" in (result["notice"] or "").lower()
    assert seen["url"] == rec["url"]
    assert result["iso_fetch"]["fetched"] is True
    assert iso_state("templeos")["sha_state"] == "verified"


def test_settings_payload_and_vm_op_flavor(tos_home, monkeypatch):
    rec = get_flavor("zealos")
    payload = b"zeal-iso"
    digest = hashlib.sha256(payload).hexdigest()
    from templeos import flavors, doctor

    monkeypatch.setitem(flavors.FLAVORS["zealos"], "sha256", digest)
    monkeypatch.setitem(flavors.FLAVORS["zealos"], "bytes", len(payload))
    monkeypatch.setattr(
        doctor,
        "download_official",
        lambda url, dest, **k: dest.write_bytes(payload) or dest,
    )

    listed = _parse(handle_vm({"op": "flavor"}))
    assert listed["ok"] is True
    assert listed["preferred_flavor"] == "templeoh"
    assert [row["id"] for row in listed["flavors"]] == ["templeoh", "tinkeros", "templeos", "zealos"]

    selected = _parse(handle_vm({"op": "flavor", "flavor": "zealos"}))
    assert selected["ok"] is True
    assert selected["preferred_flavor"] == "zealos"
    assert selected["iso_fetch"]["ok"] is True
    assert load_preferred() == "zealos"

    body = settings_payload()
    assert body["settings"]["flavor"] == "zealos"
    assert body["preferred_flavor"] == "zealos"
    switched = settings_payload({"flavor": "templeoh", "fetch": False})
    assert switched["preferred_flavor"] == "templeoh"
    assert switched["sha_state"] == "missing"
    assert load_preferred() == "templeoh"


def test_apply_config_from_ctx_settings(tos_home):
    class Ctx:
        settings = {"flavor": "tinkeros"}

    assert apply_config(Ctx()) == "tinkeros"
    assert load_preferred() == "tinkeros"


def test_status_payload_includes_picker_fields(tos_home):
    status = status_payload()
    assert status["preferred_flavor"] == "templeoh"
    assert status["sha_state"] == "missing"
    assert status["flavors"][0]["id"] == "templeoh"
    assert "sha256" in status["flavors"][0]


def test_nudge_and_cadence_defaults_and_overrides(tos_home, monkeypatch):
    from templeos.settings import (
        DEFAULT_CADENCE,
        DEFAULT_NUDGE,
        cadence_per_day,
        nudge_enabled,
    )

    monkeypatch.delenv("TEMPLEOS_NUDGE", raising=False)
    assert DEFAULT_NUDGE is True
    assert nudge_enabled() is True
    assert cadence_per_day() == DEFAULT_CADENCE == 2

    monkeypatch.setenv("TEMPLEOS_NUDGE", "off")
    assert nudge_enabled() is False
    monkeypatch.setenv("TEMPLEOS_NUDGE", "on")
    assert nudge_enabled() is True
    monkeypatch.delenv("TEMPLEOS_NUDGE", raising=False)

    (tos_home / "settings.json").write_text(
        json.dumps({"nudge": "off", "cadence": "4/day"}), encoding="utf-8"
    )
    assert nudge_enabled() is False
    assert cadence_per_day() == 4

    class Ctx:
        config = {"nudge": "on", "cadence": "1/day"}

    assert nudge_enabled(Ctx()) is True
    assert cadence_per_day(Ctx()) == 1


def test_apply_config_registers_nudge_after_companion(tos_home, monkeypatch):
    from templeos import nudge
    from tests.fakes import FakeCtx

    monkeypatch.delenv("TEMPLEOS_NUDGE", raising=False)
    nudge.reset_state()
    ctx = FakeCtx()
    apply_config(ctx)
    assert "pre_llm_call" in ctx.hooks
    nudge.record_pending(next_step="land slice")
    assert ctx.hooks["pre_llm_call"]() == "next step: land slice"


def test_bbs_enabled_setting_writes_opt_out_and_status_reflects_it(tos_home, monkeypatch):
    from templeos import bbs
    from templeos.session import bbs_status

    monkeypatch.delenv(bbs.ENV_ENABLED, raising=False)
    monkeypatch.delenv(bbs.ENV_ENDPOINT, raising=False)
    assert bbs_status()["enabled"] is True
    body = settings_payload({"bbs_enabled": False})
    assert body["ok"] is True
    assert body["bbs"]["enabled"] is False
    assert json.loads((tos_home / bbs.CONFIG_FILE).read_text())["enabled"] is False
    assert bbs.load_config(environ={}).enabled is False
    back = settings_payload({"bbs_enabled": True})
    assert back["bbs"]["enabled"] is True
