"""Keyboard, pointer, and HolyC injection.

Slice B (feat/screen-input) implements this module.

click uses QMP absolute events when VMMouse is current (TinkerOS default).
On stock TempleOS or ZealOS, absolute events error with 'input handler not
found'; use MsSet plus a button, or relative PS/2. holyc types source, or
writes it to COM1 when Comm* is live (TinkerOS after CommInit + CommInit8n1).
Cap HolyC source size.
"""

from __future__ import annotations

from typing import Any, Sequence

HOLYC_MAX_BYTES = 64 * 1024
BUTTONS = ("left", "right", "middle")
CLICK_VIA = ("auto", "vmmouse", "msset", "relative")


def type_text(text: str, *, delay_s: float = 0.09) -> dict[str, Any]:
    """Type Unicode text as QEMU qcodes (US layout, shift as needed)."""
    raise NotImplementedError("templeos.input.type_text: Slice B (feat/screen-input)")


def send_keys(keys: Sequence[str], *, hold_ms: int = 80) -> dict[str, Any]:
    """Send named QEMU qcodes (e.g. ret, esc, ctrl, a)."""
    raise NotImplementedError("templeos.input.send_keys: Slice B (feat/screen-input)")


def click(
    x: int,
    y: int,
    *,
    button: str = "left",
    via: str = "auto",
    flavor: str | None = None,
) -> dict[str, Any]:
    """Click guest coordinates. via=auto picks vmmouse, MsSet, or relative."""
    raise NotImplementedError("templeos.input.click: Slice B (feat/screen-input)")


def move(
    x: int,
    y: int,
    *,
    via: str = "auto",
    flavor: str | None = None,
) -> dict[str, Any]:
    """Move the pointer to guest coordinates without a click."""
    raise NotImplementedError("templeos.input.move: Slice B (feat/screen-input)")


def holyc(source: str, *, via: str = "auto") -> dict[str, Any]:
    """Send HolyC. Prefer COM1 when Comm* is live, else type it.

    ``via`` is auto, serial, or type. Reject sources larger than HOLYC_MAX_BYTES.
    """
    raise NotImplementedError("templeos.input.holyc: Slice B (feat/screen-input)")
