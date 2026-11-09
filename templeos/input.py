"""Keyboard, pointer, and HolyC injection.

Slice B (feat/screen-input) implements this module.

click uses QMP absolute events when VMMouse is current (TinkerOS default).
On stock TempleOS or ZealOS, absolute events error with 'input handler not
found'; use MsSet plus a button, or relative PS/2. holyc types source, or
writes it to COM1 when Comm* is live (TinkerOS after CommInit + CommInit8n1).
Cap HolyC source size.
"""

from __future__ import annotations

import time
from typing import Any, Sequence

from templeos.arbiter import get_arbiter
from templeos.flavors import DEFAULT, guest_size, mouse_strategy
from templeos.screen import bind, get_runtime, require_runtime, unbind
from templeos.tools import CODE_FIX, Code

# Re-export so tests and Slice A can bind a session from either module.
__all__ = (
    "HOLYC_MAX_BYTES",
    "BUTTONS",
    "CLICK_VIA",
    "CMD_LINE",
    "bind",
    "unbind",
    "type_text",
    "send_keys",
    "click",
    "move",
    "holyc",
    "qcodes_for",
)

HOLYC_MAX_BYTES = 64 * 1024
BUTTONS = ("left", "right", "middle")
CLICK_VIA = ("auto", "vmmouse", "msset", "relative")
HOLYC_VIA = ("auto", "serial", "type")
DEFAULT_DELAY_S = 0.09
DEFAULT_HOLD_MS = 80
CHUNK_CHARS = 32
ABS_MAX = 32767
# Bake-off: a click on 'Cmd Line' at this pixel opened Command Line Overview.
CMD_LINE = (255, 51)

# US layout. Shift is implied as the first qcode for entries in SHIFT_MAP.
SHIFT_MAP: dict[str, str] = {
    "A": "a",
    "B": "b",
    "C": "c",
    "D": "d",
    "E": "e",
    "F": "f",
    "G": "g",
    "H": "h",
    "I": "i",
    "J": "j",
    "K": "k",
    "L": "l",
    "M": "m",
    "N": "n",
    "O": "o",
    "P": "p",
    "Q": "q",
    "R": "r",
    "S": "s",
    "T": "t",
    "U": "u",
    "V": "v",
    "W": "w",
    "X": "x",
    "Y": "y",
    "Z": "z",
    '"': "apostrophe",
    ":": "semicolon",
    "_": "minus",
    "+": "equal",
    "{": "bracket_left",
    "}": "bracket_right",
    "|": "backslash",
    "<": "comma",
    ">": "dot",
    "?": "slash",
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "~": "grave_accent",
}

PLAIN_MAP: dict[str, str] = {
    " ": "spc",
    "\n": "ret",
    "\r": "ret",
    "\t": "tab",
    "\b": "backspace",
    "-": "minus",
    "=": "equal",
    "[": "bracket_left",
    "]": "bracket_right",
    "\\": "backslash",
    ";": "semicolon",
    "'": "apostrophe",
    ",": "comma",
    ".": "dot",
    "/": "slash",
    "`": "grave_accent",
}

KEY_ALIASES: dict[str, str] = {
    "enter": "ret",
    "return": "ret",
    "space": "spc",
    "spacebar": "spc",
    "escape": "esc",
    "control": "ctrl",
    "ctl": "ctrl",
    "ctrl_l": "ctrl",
    "alt_l": "alt",
    "shift_l": "shift",
    "pg_up": "pgup",
    "page_up": "pgup",
    "pageup": "pgup",
    "pg_down": "pgdn",
    "page_down": "pgdn",
    "pagedown": "pgdn",
    "bs": "backspace",
    "del": "delete",
}

# Known atomic qcodes that contain a hyphen and must not be split as combos.
ATOMIC_QCODES = frozenset(
    {
        "shift_r",
        "shift_l",
        "ctrl_r",
        "ctrl_l",
        "alt_r",
        "alt_l",
        "meta_l",
        "meta_r",
        "caps_lock",
        "num_lock",
        "scroll_lock",
        "kp_enter",
        "kp_decimal",
        "kp_add",
        "kp_subtract",
        "kp_multiply",
        "kp_divide",
        "kp_minus",
        "kp_plus",
        "bracket_left",
        "bracket_right",
        "grave_accent",
        "back_space",
        "page_up",
        "page_down",
        "print_screen",
        "sysrq",
    }
)


def qcodes_for(ch: str) -> list[str]:
    """Map a single Unicode character to a US-layout QEMU qcode chord."""
    if not ch:
        raise ValueError("empty character")
    if ch in SHIFT_MAP:
        return ["shift", SHIFT_MAP[ch]]
    if ch in PLAIN_MAP:
        return [PLAIN_MAP[ch]]
    if "a" <= ch <= "z" or "0" <= ch <= "9":
        return [ch]
    raise ValueError(f"no QEMU qcode for {ch!r} on the US layout")


def _fail(message: str, code: str, **fields: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "error": message,
        "code": code,
        "fix": CODE_FIX.get(code, "See docs/CONTRACTS.md."),
        **fields,
    }


def _ok(**fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": True}
    body.update(fields)
    return body


def _require_qmp() -> Any:
    """Bound QMP, or the Slice B NotImplementedError when nothing is attached."""
    return require_runtime().qmp


def _send_key(qmp: Any, codes: Sequence[str], *, hold_ms: int = DEFAULT_HOLD_MS) -> None:
    names = [str(c) for c in codes]
    if hasattr(qmp, "send_key"):
        qmp.send_key(list(names), hold_ms=hold_ms)
    else:
        keys = [{"type": "qcode", "data": c} for c in names]
        qmp.cmd("send-key", keys=keys, **{"hold-time": hold_ms})
    # send-key can leave Shift latched on TinkerOS; release both shift keys.
    if any(c in {"shift", "shift_r", "shift_l"} for c in names):
        _unstick_shift(qmp)


def _input_events(qmp: Any, events: list[dict[str, Any]]) -> None:
    if hasattr(qmp, "input_send_event"):
        qmp.input_send_event(events)
    else:
        qmp.cmd("input-send-event", events=events)


def _unstick_shift(qmp: Any) -> None:
    try:
        _input_events(
            qmp,
            [
                {"type": "key", "data": {"down": False, "key": {"type": "qcode", "data": "shift"}}},
                {"type": "key", "data": {"down": False, "key": {"type": "qcode", "data": "shift_r"}}},
            ],
        )
    except Exception:
        pass


def _parse_combo(token: str) -> list[str]:
    raw = (token or "").strip()
    if not raw:
        raise ValueError("empty key name")
    lower = raw.lower()
    alias = KEY_ALIASES.get(lower, lower)
    if alias in ATOMIC_QCODES or lower in ATOMIC_QCODES:
        return [KEY_ALIASES.get(alias, alias)]
    if "+" in raw:
        parts = [p.strip() for p in raw.split("+") if p.strip()]
    elif "-" in raw and lower not in ATOMIC_QCODES and lower not in KEY_ALIASES:
        parts = [p.strip() for p in raw.split("-") if p.strip()]
    else:
        parts = [raw]
    codes: list[str] = []
    for part in parts:
        name = KEY_ALIASES.get(part.lower(), part.lower())
        if not name:
            raise ValueError(f"empty key in combo {token!r}")
        codes.append(name)
    if not codes:
        raise ValueError(f"empty key name {token!r}")
    return codes


def type_text(text: str, *, delay_s: float = DEFAULT_DELAY_S) -> dict[str, Any]:
    """Type Unicode text as QEMU qcodes (US layout, shift as needed)."""
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    arbiter = get_arbiter()
    with arbiter.queue():
        qmp = _require_qmp()
        typed = 0
        for i, ch in enumerate(text):
            codes = qcodes_for(ch)
            _send_key(qmp, codes)
            typed += 1
            if delay_s > 0:
                time.sleep(delay_s)
                if CHUNK_CHARS and (i + 1) % CHUNK_CHARS == 0:
                    time.sleep(delay_s)
        return _ok(typed=typed)


def send_keys(keys: Sequence[str], *, hold_ms: int = DEFAULT_HOLD_MS) -> dict[str, Any]:
    """Send named QEMU qcodes (e.g. ret, esc, ctrl, a)."""
    if not keys:
        raise ValueError("keys must be a non-empty sequence of qcode names")
    combos = [_parse_combo(k) for k in keys]
    arbiter = get_arbiter()
    with arbiter.queue():
        qmp = _require_qmp()
        sent: list[list[str]] = []
        for codes in combos:
            _send_key(qmp, codes, hold_ms=hold_ms)
            sent.append(list(codes))
        return _ok(keys=sent)


def _abs_axis(px: int, size: int) -> int:
    if size <= 0:
        return 0
    return max(0, min(ABS_MAX, int(px * ABS_MAX / size)))


def _flavor_size(flavor: str | None) -> tuple[int, int]:
    try:
        return guest_size(flavor)
    except Exception:
        return (640, 480)


def _abs_events(x: int, y: int, width: int, height: int) -> list[dict[str, Any]]:
    return [
        {"type": "abs", "data": {"axis": "x", "value": _abs_axis(x, width)}},
        {"type": "abs", "data": {"axis": "y", "value": _abs_axis(y, height)}},
    ]


def _rel_events(dx: int, dy: int) -> list[dict[str, Any]]:
    return [
        {"type": "rel", "data": {"axis": "x", "value": int(dx)}},
        {"type": "rel", "data": {"axis": "y", "value": int(dy)}},
    ]


def _btn_events(button: str, *, down: bool) -> list[dict[str, Any]]:
    return [{"type": "btn", "data": {"down": bool(down), "button": button}}]


def _pointer_via(via: str, flavor: str | None) -> str:
    if via not in CLICK_VIA:
        raise ValueError(f"via must be one of {', '.join(CLICK_VIA)}, not {via!r}")
    if via != "auto":
        return via
    return mouse_strategy(flavor or DEFAULT)


def _move_vmmouse(qmp: Any, x: int, y: int, width: int, height: int) -> dict[str, Any]:
    events = _abs_events(x, y, width, height)
    _input_events(qmp, events)
    return {
        "via": "vmmouse",
        "x": x,
        "y": y,
        "abs": [_abs_axis(x, width), _abs_axis(y, height)],
    }


def _move_relative(qmp: Any, x: int, y: int, last: tuple[int, int] | None) -> dict[str, Any]:
    origin = last or (0, 0)
    dx = int(x) - int(origin[0])
    dy = int(y) - int(origin[1])
    _input_events(qmp, _rel_events(dx, dy))
    return {"via": "relative", "x": x, "y": y, "dx": dx, "dy": dy}


def _move_msset(x: int, y: int, *, delay_s: float) -> dict[str, Any]:
    # HolyC fallback for flavors without absolute input. Runs at the prompt.
    source = f"MsSet({int(x)},{int(y)});"
    typed = type_text(source + "\n", delay_s=delay_s)
    if typed.get("ok") is False:
        return typed
    return {"via": "msset", "x": x, "y": y, "source": source}


def _click_button(qmp: Any, button: str, *, hold_s: float = 0.0) -> None:
    _input_events(qmp, _btn_events(button, down=True))
    if hold_s > 0:
        time.sleep(hold_s)
    _input_events(qmp, _btn_events(button, down=False))


def _apply_move(
    *,
    x: int,
    y: int,
    via: str,
    flavor: str | None,
    qmp: Any,
    last: tuple[int, int] | None,
    delay_s: float,
) -> dict[str, Any]:
    width, height = _flavor_size(flavor)
    strategy = _pointer_via(via, flavor)
    if strategy == "vmmouse":
        try:
            return _move_vmmouse(qmp, x, y, width, height)
        except Exception as exc:
            if via == "auto" and "input handler not found" in str(exc).lower():
                # Proven stock-TempleOS fallback: MsSet plus a later button.
                return _move_msset(x, y, delay_s=delay_s)
            raise
    if strategy == "msset":
        return _move_msset(x, y, delay_s=delay_s)
    if strategy == "relative":
        return _move_relative(qmp, x, y, last)
    raise ValueError(f"unknown pointer strategy {strategy!r}")


def click(
    x: int,
    y: int,
    *,
    button: str = "left",
    via: str = "auto",
    flavor: str | None = None,
) -> dict[str, Any]:
    """Click guest coordinates. via=auto picks vmmouse, MsSet, or relative."""
    if button not in BUTTONS:
        raise ValueError("button must be left, right, or middle.")
    if not isinstance(x, int) or not isinstance(y, int):
        raise ValueError("x and y must be integers")
    arbiter = get_arbiter()
    with arbiter.queue():
        rt = require_runtime()
        qmp = rt.qmp
        used_flavor = flavor or rt.flavor
        delay = 0.0 if rt.type_delay_s is None else min(rt.type_delay_s, DEFAULT_DELAY_S)
        # MsSet types at the HolyC prompt; keep that path snappy in tests.
        try:
            info = _apply_move(
                x=x,
                y=y,
                via=via,
                flavor=used_flavor,
                qmp=qmp,
                last=rt.last_pointer,
                delay_s=0.0 if delay == 0.09 else delay,
            )
        except Exception as exc:
            if "input handler not found" in str(exc).lower():
                return _fail(str(exc), Code.INVALID_ARGS, via=via, x=x, y=y)
            raise
        if info.get("ok") is False:
            return info
        # Bake-off: wait after the absolute move, then a short button hold.
        # Keep this at zero when type_delay_s is 0 so unit tests stay fast.
        settle = 0.0 if not rt.type_delay_s else max(0.25, float(rt.type_delay_s) * 3)
        hold = 0.0 if not rt.type_delay_s else 0.15
        if settle:
            time.sleep(settle)
        _click_button(qmp, button, hold_s=hold)
        rt.last_pointer = (x, y)
        return _ok(button=button, **info)


def move(
    x: int,
    y: int,
    *,
    via: str = "auto",
    flavor: str | None = None,
) -> dict[str, Any]:
    """Move the pointer to guest coordinates without a click."""
    if not isinstance(x, int) or not isinstance(y, int):
        raise ValueError("x and y must be integers")
    arbiter = get_arbiter()
    with arbiter.queue():
        rt = require_runtime()
        qmp = rt.qmp
        used_flavor = flavor or rt.flavor
        try:
            info = _apply_move(
                x=x,
                y=y,
                via=via,
                flavor=used_flavor,
                qmp=qmp,
                last=rt.last_pointer,
                delay_s=0.0,
            )
        except Exception as exc:
            if "input handler not found" in str(exc).lower():
                return _fail(str(exc), Code.INVALID_ARGS, via=via, x=x, y=y)
            raise
        if info.get("ok") is False:
            return info
        rt.last_pointer = (x, y)
        return _ok(**info)


def _serial_ready(serial: Any) -> bool:
    return serial is not None and bool(getattr(serial, "connected", False))


def holyc(source: str, *, via: str = "auto") -> dict[str, Any]:
    """Send HolyC. Prefer COM1 when Comm* is live, else type it.

    ``via`` is auto, serial, or type. Reject sources larger than HOLYC_MAX_BYTES.
    """
    if not isinstance(source, str) or source == "":
        raise ValueError("holyc requires a non-empty source string")
    if via not in HOLYC_VIA:
        raise ValueError(f"via must be one of {', '.join(HOLYC_VIA)}, not {via!r}")
    size = len(source.encode("utf-8"))
    if size > HOLYC_MAX_BYTES:
        return _fail(
            f"HolyC source exceeds {HOLYC_MAX_BYTES} bytes.",
            Code.INVALID_ARGS,
            bytes=size,
        )
    payload = source if source.endswith("\n") else source + "\n"
    arbiter = get_arbiter()
    with arbiter.queue():
        rt = require_runtime()
        serial = rt.serial
        use_serial = via == "serial" or (via == "auto" and _serial_ready(serial))
        if via == "serial" and not _serial_ready(serial):
            return _fail(
                "COM1 is not open. Keep the serial socket connected and, on TinkerOS, call CommInit then CommInit8n1.",
                Code.SERIAL_NOT_READY,
                via=via,
            )
        if use_serial and _serial_ready(serial):
            try:
                serial.write(payload.encode("utf-8"))
            except Exception as exc:
                return _fail(str(exc) or "Serial write failed.", Code.SERIAL_NOT_READY, via="serial")
            return _ok(via="serial", bytes=len(payload.encode("utf-8")))
        typed = type_text(payload, delay_s=0.0 if rt.type_delay_s == 0.09 else rt.type_delay_s)
        if typed.get("ok") is False:
            return typed
        return _ok(via="type", typed=typed.get("typed"), bytes=len(payload.encode("utf-8")))
