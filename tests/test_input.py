"""Slice B input: qcode mapping, pointer strategies, holyc, and the arbiter queue."""

from __future__ import annotations

import threading
import time

import pytest

from templeos.arbiter import Arbiter, get_arbiter, reset_arbiter
from templeos.input import (
    CMD_LINE,
    HOLYC_MAX_BYTES,
    click,
    holyc,
    move,
    qcodes_for,
    send_keys,
    type_text,
    unbind,
)
from templeos.screen import bind
from templeos.tools import handle_input
from tests.fakes import MIN_PNG, FakeQMP, FakeSerial


@pytest.fixture(autouse=True)
def _reset_runtime(tos_home):
    unbind()
    reset_arbiter()
    yield
    unbind()
    reset_arbiter()


def _bind(
    tos_home,
    *,
    flavor: str = "tinkeros",
    serial=None,
    abs_mouse: bool = True,
    last_pointer=None,
    type_delay_s: float = 0,
    accel: str | None = None,
):
    qmp = FakeQMP(abs_mouse=abs_mouse)
    qmp.connect(tos_home / "qmp.sock")
    qmp.framebuffer = MIN_PNG
    if accel:
        qmp.accel = accel
    bind(
        qmp=qmp,
        serial=serial,
        flavor=flavor,
        state_dir=tos_home,
        last_pointer=last_pointer,
        type_delay_s=type_delay_s,
    )
    return qmp


def test_unbound_input_returns_vm_not_running():
    for body in (
        type_text("Hi"),
        send_keys(["ret"]),
        click(1, 2),
        move(1, 2),
        holyc("Dir;"),
    ):
        assert body["ok"] is False
        assert body["code"] == "vm_not_running"


def test_qcodes_for_letters_shift_and_holyc_punctuation():
    assert qcodes_for("h") == ["h"]
    assert qcodes_for("H") == ["shift", "h"]
    assert qcodes_for(" ") == ["spc"]
    assert qcodes_for("\n") == ["ret"]
    assert qcodes_for('"') == ["shift", "apostrophe"]
    assert qcodes_for(";") == ["semicolon"]
    assert qcodes_for("\\") == ["backslash"]
    assert qcodes_for("(") == ["shift", "9"]
    assert qcodes_for(")") == ["shift", "0"]
    assert qcodes_for("_") == ["shift", "minus"]
    assert qcodes_for("~") == ["shift", "grave_accent"]
    assert qcodes_for("#") == ["shift", "3"]
    with pytest.raises(ValueError, match="qcode"):
        qcodes_for("€")


def test_type_text_records_send_key_chords(tos_home):
    qmp = _bind(tos_home)
    result = type_text('"Hello\\n";', delay_s=0)
    assert result["ok"] is True
    assert result["typed"] == len('"Hello\\n";')
    # The HolyC source is quote + Hello + backslash + n + quote + semicolon.
    assert qmp.keys[0] == ["shift", "apostrophe"]
    assert qmp.keys[1] == ["shift", "h"]
    assert qmp.keys[2] == ["e"]
    assert qmp.keys[3] == ["l"]
    assert qmp.keys[4] == ["l"]
    assert qmp.keys[5] == ["o"]
    assert qmp.keys[6] == ["backslash"]
    assert qmp.keys[7] == ["n"]
    assert qmp.keys[8] == ["shift", "apostrophe"]
    assert qmp.keys[9] == ["semicolon"]


def test_shift_chords_send_down_then_up_events(tos_home):
    qmp = _bind(tos_home)
    result = type_text('"', delay_s=0)
    assert result["ok"] is True
    key_batches = [batch for batch in qmp.events if batch and batch[0].get("type") == "key"]
    assert len(key_batches) >= 2
    downs, ups = key_batches[0], key_batches[1]
    assert [ev["data"]["key"]["data"] for ev in downs] == ["shift", "apostrophe"]
    assert all(ev["data"]["down"] for ev in downs)
    assert [ev["data"]["key"]["data"] for ev in ups] == ["apostrophe", "shift"]
    assert all(not ev["data"]["down"] for ev in ups)
    assert qmp.keys[0] == ["shift", "apostrophe"]


def test_tcg_shift_chord_keeps_the_p4_sequential_down_up_path(tos_home):
    # P4 regression guard: under TCG a shifted chord is pressed down in order,
    # held, then released in reverse. Do not fold it back into one batch.
    qmp = _bind(tos_home, type_delay_s=0.09, accel="tcg")
    result = type_text('"', delay_s=0.12)
    assert result["ok"] is True
    key_batches = [batch for batch in qmp.events if batch and batch[0].get("type") == "key"]
    first_two = key_batches[:2]
    assert [batch[0]["data"]["key"]["data"] for batch in first_two] == ["shift", "apostrophe"]
    assert all(batch[0]["data"]["down"] for batch in first_two)
    up_codes = [
        ev["data"]["key"]["data"]
        for batch in key_batches[2:]
        for ev in batch
        if not ev["data"]["down"]
    ]
    assert up_codes[:2] == ["apostrophe", "shift"]


def test_send_keys_parses_combos_and_esc(tos_home):
    qmp = _bind(tos_home)
    result = send_keys(["ctrl+alt+x", "esc"], hold_ms=0)
    assert result["ok"] is True
    assert result["keys"] == [["ctrl", "alt", "x"], ["esc"]]
    assert qmp.keys == [["ctrl", "alt", "x"], ["esc"]]
    send_keys(["enter"])
    assert qmp.keys[-1] == ["ret"]


def test_click_vmmouse_uses_absolute_input(tos_home):
    qmp = _bind(tos_home, flavor="tinkeros")
    x, y = CMD_LINE
    result = click(x, y, via="vmmouse", flavor="tinkeros")
    assert result["ok"] is True
    assert result["via"] == "vmmouse"
    assert result["abs"] == [int(x * 32767 / 640), int(y * 32767 / 480)]
    # Move first, then button down / up.
    kinds = [ev["type"] for batch in qmp.events for ev in batch]
    assert "abs" in kinds and "btn" in kinds
    abs_vals = [
        (ev["data"]["axis"], ev["data"]["value"])
        for batch in qmp.events
        for ev in batch
        if ev["type"] == "abs"
    ]
    assert ("x", result["abs"][0]) in abs_vals
    assert ("y", result["abs"][1]) in abs_vals


def test_auto_falls_back_to_msset_when_abs_is_missing(tos_home):
    qmp = _bind(tos_home, flavor="tinkeros", abs_mouse=False)
    result = click(255, 51, via="auto", flavor="tinkeros")
    assert result["ok"] is True
    assert result["via"] == "msset"
    # MsSet(255,51);\n was typed, then a button event went out.
    flat = [c for chord in qmp.keys for c in chord]
    assert "m" in [c.lower() for c in flat] or qmp.keys
    assert any(ev[0]["type"] == "btn" for ev in qmp.events if ev)
    # Explicit vmmouse does not silently fall back.
    qmp2 = _bind(tos_home, flavor="tinkeros", abs_mouse=False)
    denied = click(255, 51, via="vmmouse", flavor="tinkeros")
    assert denied["ok"] is False


def test_msset_and_relative_strategies(tos_home):
    qmp = _bind(tos_home, flavor="templeos")
    result = move(100, 80, via="auto", flavor="templeos")
    assert result["ok"] is True
    assert result["via"] == "msset"
    assert "MsSet(100,80)" in (result.get("source") or "")
    assert qmp.keys  # typed HolyC

    qmp = _bind(tos_home, flavor="zealos", last_pointer=(0, 0))
    moved = move(10, 20, via="auto", flavor="zealos")
    assert moved["ok"] is True
    assert moved["via"] == "relative"
    assert moved["dx"] == 10 and moved["dy"] == 20
    rel = [ev for batch in qmp.events for ev in batch if ev["type"] == "rel"]
    assert rel[0]["data"]["value"] == 10
    assert rel[1]["data"]["value"] == 20


def test_holyc_auto_prefers_type_until_guest_serial_ready(tos_home):
    # Host COM1 open alone must NOT make auto choose serial — guest Comm* is
    # required (Runtime.guest_serial_ready) or an explicit via=serial.
    serial = FakeSerial()
    serial.open(tos_home / "com1.sock")
    qmp = _bind(tos_home, serial=serial)
    result = holyc("Dir;", via="auto")
    assert result["ok"] is True
    assert result["via"] == "type"
    assert serial.tx == b""
    assert qmp.keys  # typed at the HolyC prompt

    from templeos.screen import get_runtime

    rt = get_runtime()
    assert rt is not None
    rt.guest_serial_ready = True
    serial2 = FakeSerial()
    serial2.open(tos_home / "com1.sock")
    _bind(tos_home, serial=serial2)
    get_runtime().guest_serial_ready = True
    ready = holyc("Dir;", via="auto")
    assert ready["ok"] is True
    assert ready["via"] == "serial"
    assert serial2.tx.endswith(b"Dir;\n")

    missing = FakeSerial()
    _bind(tos_home, serial=missing)
    denied = holyc("Dir;", via="serial")
    assert denied["ok"] is False
    assert denied["code"] == "serial_not_ready"

    _bind(tos_home, serial=None)
    typed = holyc("DocClear;", via="type")
    assert typed["ok"] is True
    assert typed["via"] == "type"

    huge = holyc("x" * (HOLYC_MAX_BYTES + 1))
    assert huge["ok"] is False
    assert huge["code"] == "invalid_args"


def test_holyc_tcg_uses_slow_per_key_typing_by_default(tos_home):
    # P5 evidence: default-speed HolyC typing garbled under TCG. op=holyc must
    # select the P4 per-key route with a slower inter-key gap, not a batched
    # send-key chord, without any monkeypatch of the input helpers.
    qmp = _bind(tos_home, type_delay_s=0.09, accel="tcg")
    result = holyc('"Hi";', via="type")
    assert result["ok"] is True
    assert result["via"] == "type"
    assert result["accel"] == "tcg"
    assert result["per_key"] is True
    assert result["delay_s"] >= 0.12
    # The slow path sends each qcode down as its own event, so the recording
    # is flat shift/apostrophe/... rather than a batched chord.
    flat = [code for chord in qmp.keys for code in chord]
    assert flat == [
        "shift", "apostrophe",
        "shift", "h",
        "i",
        "shift", "apostrophe",
        "semicolon",
        "ret",
    ]
    # Every key-down uses its own input-send-event: the slow TCG path.
    key_batches = [batch for batch in qmp.events if batch and batch[0].get("type") == "key"]
    assert key_batches
    down_batches = [
        batch
        for batch in key_batches
        if any(ev["data"]["down"] for ev in batch)
    ]
    assert len(down_batches) == len(flat)
    assert all(len(batch) == 1 for batch in down_batches)


def test_holyc_kvm_keeps_the_fast_typing_path(tos_home):
    qmp = _bind(tos_home, type_delay_s=0.09, accel="kvm")
    result = holyc('"Hi";', via="type")
    assert result["ok"] is True
    assert result["accel"] == "kvm"
    assert result["per_key"] is False
    assert result["delay_s"] <= 0.05
    # KVM keeps batched chords and ends with the newline's ret key.
    assert qmp.keys[0] == ["shift", "apostrophe"]
    assert qmp.keys[-1] == ["ret"]


def test_holyc_zero_delay_unit_seam_stays_instant(tos_home):
    _bind(tos_home, type_delay_s=0, accel="tcg")
    result = holyc("Dir;", via="type")
    assert result["ok"] is True
    assert result["delay_s"] == 0.0
    assert result["per_key"] is False


def test_input_goes_through_the_arbiter_queue(tos_home):
    qmp = _bind(tos_home)
    # Direct calls still serialize on the arbiter lock, but they do not
    # apply agent_paused themselves: api.user_input notes a user event and
    # then calls type_text, and handle_input already returns agent_paused.
    get_arbiter().take_control()
    result = type_text("A", delay_s=0)
    assert result["ok"] is True
    assert qmp.keys[-1] == ["shift", "a"]

    held = []
    released = threading.Event()
    started = threading.Event()

    def holder():
        arb = get_arbiter()
        with arb.queue():
            started.set()
            released.wait(timeout=2)

    thread = threading.Thread(target=holder)
    thread.start()
    assert started.wait(timeout=2)
    t0 = time.monotonic()
    # Release after a short hold so type_text can proceed.
    def releaser():
        time.sleep(0.05)
        released.set()

    threading.Thread(target=releaser).start()
    typed = type_text("b", delay_s=0)
    waited = time.monotonic() - t0
    thread.join(timeout=2)
    assert typed["ok"] is True
    assert waited >= 0.04
    # Agent tools still see agent_paused while the user has control.
    body = __import__("json").loads(handle_input({"op": "type", "text": "Hi"}))
    assert body["ok"] is False and body["code"] == "agent_paused"


def test_handle_input_types_when_the_agent_has_control(tos_home):
    qmp = _bind(tos_home)
    reset_arbiter(Arbiter())
    body = __import__("json").loads(handle_input({"op": "keys", "keys": ["esc"]}))
    assert body["ok"] is True
    assert qmp.keys[-1] == ["esc"]
