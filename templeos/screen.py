"""Screendump, PNG frames, cropped hashes, wait_idle, and 8x8 glyph text.

Slice B (feat/screen-input) implements this module.

Prefer PNG over JPEG at these palettes. Full-frame hashes never stabilize
because of the title-bar clock and FPS; use flavors.hash_crop. Default
look is 640x480 (ZealOS is 1024x768, about 2.5× the visual tokens).
read_text prefers serial when COM1 is already open, else 8x8 glyph match
on the 80x60 (or matching) grid.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def look(*, dest: Path | None = None) -> dict[str, Any]:
    """Return a PNG frame: width, height, mime, sha256, data (base64), caption.

    Budget the whole serialized JSON (base64 included) under the 512 KiB
    pane relay limit and fail with payload_too_large rather than truncate.
    """
    raise NotImplementedError("templeos.screen.look: Slice B (feat/screen-input)")


def read_text() -> dict[str, Any]:
    """Return {text, source} where source is serial or glyphs."""
    raise NotImplementedError("templeos.screen.read_text: Slice B (feat/screen-input)")


def wait_idle(*, timeout_s: float = 5.0, crop: dict[str, int] | None = None) -> dict[str, Any]:
    """Wait until the cropped frame hash is stable, or time out."""
    raise NotImplementedError("templeos.screen.wait_idle: Slice B (feat/screen-input)")


def frame_hash(*, crop: dict[str, int] | None = None) -> dict[str, Any]:
    """SHA-256 of the cropped framebuffer (not the chrome clock)."""
    raise NotImplementedError("templeos.screen.frame_hash: Slice B (feat/screen-input)")


def glyph_read(image: Path | bytes) -> str:
    """Match official 8x8 glyphs on a screendump. Used when serial is silent."""
    raise NotImplementedError("templeos.screen.glyph_read: Slice B (feat/screen-input)")
