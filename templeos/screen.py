"""Screendump, PNG frames, cropped hashes, wait_idle, and 8x8 glyph text.

Slice B (feat/screen-input) implements this module.

Prefer PNG over JPEG at these palettes. Full-frame hashes never stabilize
because of the title-bar clock and FPS; use flavors.hash_crop. Default
look is 640x480 (ZealOS is 1024x768, about 2.5x the visual tokens).
read_text prefers serial when COM1 is already open, else 8x8 glyph match
on the 80x60 (or matching) grid.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from templeos.flavors import DEFAULT, hash_crop as flavor_hash_crop
from templeos.paths import ensure_layout, frames_dir
from templeos.tools import CODE_FIX, Code

try:
    from PIL import Image
except ImportError:  # pragma: no cover - add pillow>=10,<12 to the plugin pin
    Image = None  # type: ignore[assignment]


# Public-domain TinkerOS/TempleOS sys_font_std (Kernel/FontStd.HC).
# 256 glyphs, 16 hex chars each (little-endian U64). Low byte is the top
# row; the least-significant bit of each row byte is the leftmost pixel.
_STD_FONT_HEX = (
    "00000000000000000000000000000000000000ff00000000000000ff00ff0000"
    "18181818181818186c6c6c6c6c6c6c6c181818f8000000006c6c6cec0cfc0000"
    "1818181f000000006c6c6c6f607f0000000000f818181818000000fc0cec6c6c"
    "0000001f181818180000007f606f6c6c00000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000008000000000000"
    "000000000000000000180018183c3c180000000000363636006c6cfe6cfe6c6c"
    "00187ed07c16fc300060660c1830660600dc66b61c36361c0000000000181818"
    "0030180c0c0c1830000c18303030180c0000187e3c7e1800000018187e181800"
    "0c18180000000000000000007e00000000181800000000000000060c18306000"
    "003c666e7e76663c007e181818181c18007e0c183060663c003c66603860663c"
    "0030307e363c3830003c6660603e067e003c66663e060c38000c0c0c1830607e"
    "003c66663c66663c001c30607c66663c00181800181800000c18180018180000"
    "0030180c060c18300000007e007e0000000c18306030180c001800181830663c"
    "003c06765676663c006666667e66663c003e66663e66663e003c66060606663c"
    "001e36666666361e007e06063e06067e000606063e06067e003c66667606663c"
    "006666667e666666007e18181818187e001c36303030307c0066361e0e1e3666"
    "007e06060606060600c6c6d6d6feeec6006666767e6e6666003c66666666663c"
    "000606063e66663e006c36566666663c006666363e66663e003c66603c06663c"
    "001818181818187e003c66666666666600183c666666666600c6eefed6d6c6c6"
    "0066663c183c6666001818183c666666007e060c1830607e003e06060606063e"
    "00006030180c0600007c60606060607c000000000000663cffff000000000000"
    "000000000030180c007c667c603c0000003e6666663e0606003c6606663c0000"
    "007c6666667c6060003c067e663c0000000c0c0c3e0c0c383c607c66667c0000"
    "00666666663e0606003c1818181c00180e181818181c00180066361e36660606"
    "003c18181818181c00c6d6d6fe6c000000666666663e0000003c6666663c0000"
    "06063e66663e0000e0607c66667c0000000606066e360000003e603c067c0000"
    "00380c0c0c3e0c0c007c66666666000000183c6666660000006cfed6d6c60000"
    "00663c183c6600003c607c6666660000007e0c18307e0000003018180e181830"
    "0018181818181818000c18187018180c000000000062d68cffffffffffffffff"
    "1e30181e3303331e007e333333003300001e033f331e003800fc667c603cc37e"
    "007e333e301e0033007e333e301e0007007e333e301e0c0c3c603e03033e0000"
    "003c067e663cc37e001e033f331e0033001e033f331e0007001e0c0c0c0e0033"
    "003c1818181c633e001e0c0c0c0e000700333f33331e0c3300333f331e000c0c"
    "003f061e063f003800fe33fe30fe0000007333337f33367c001e33331e00331e"
    "001e33331e003300001e33331e000700007e33333300331e007e333333000700"
    "1f303f3333003300001c3e63633e1c63001e33333333003318187e03037e1818"
    "003f67060f26361c000c3f0c3f1e333370337b332f1b1b0f0e1b18187e18d870"
    "007e333e301e0038001e0c0c0c0e001c001e33331e003800007e333333003800"
    "003333331f001f0000333b3f3733003f00007e007c36363c00007e003c66663c"
    "001e3303060c000c000003033f000000000030303f000000f81973c67c1b3363"
    "c0f9f3e6cf1b3363183c3c18180018000000cc663366cc0000003366cc663300"
    "114411441144114455aa55aa55aa55aaeebbeebbeebbeebb1818181818181818"
    "1818181f181818181818181f181f18186c6c6c6f6c6c6c6c6c6c6c7f00000000"
    "1818181f181f00006c6c6c6f606f6c6c6c6c6c6c6c6c6c6c6c6c6c6f607f0000"
    "0000007f606f6c6c0000007f6c6c6c6c0000001f181f18181818181f00000000"
    "000000f818181818000000ff18181818181818ff00000000181818f818181818"
    "000000ff00000000181818ff18181818181818f818f818186c6c6cec6c6c6c6c"
    "000000fc0cec6c6c6c6c6cec0cfc0000000000ff00ef6c6c6c6c6cef00ff0000"
    "6c6c6cec0cec6c6c000000ff00ff00006c6c6cef00ef6c6c000000ff00ff1818"
    "000000ff6c6c6c6c181818ff00ff00006c6c6cff00000000000000fc6c6c6c6c"
    "000000f818f81818181818f818f800006c6c6cfc000000006c6c6cef6c6c6c6c"
    "181818ff00ff18180000001f18181818181818f800000000ffffffffffffffff"
    "ffffffff000000000f0f0f0f0f0f0f0ff0f0f0f0f0f0f0f000000000ffffffff"
    "006e3b133b6e000003031f331f331e000003030303637f000036363636367f00"
    "007f660c180c667f001e3333337e000003063e666666660000181818183b6e00"
    "3f0c1e33331e0c3f001c36637f63361c007736366363361c001e33333e180c38"
    "00007edbdb7e000003067edbdb7e3060003c06033f03063c003333333333331e"
    "00003f003f003f00003f000c0c3f0c0c003f00060c180c06003f00180c060c18"
    "1818181818d8d8700e1b1b1818181818000c0c003f000c0c0000394e00394e00"
    "000000001c36361c00000018180000000000001800000000383c3637303030f0"
    "000000363636361e0000003e061c301e00003c3c3c3c0000ffffffffffffffff"
)
STD_FONT: tuple[int, ...] = tuple(
    int(_STD_FONT_HEX[i : i + 16], 16) for i in range(0, len(_STD_FONT_HEX), 16)
)
assert len(STD_FONT) == 256

# Sparse ZealOS 8x8 table harvested from a 1024x768 bake-off screendump.
# Stem weights differ from FontStd; do not mix the two tables.
ZEAL_FONT: dict[int, int] = {
    34: 0x0000000000123636,
    35: 0x00c9c980c980c9c9,
    38: 0x0091ccc491e3c9e3,
    39: 0x0000000000040c0c,
    40: 0x00180c0606060c18,
    41: 0x00060c1818180c06,
    44: 0x060c0c0c00000000,
    46: 0x000c0c0000000000,
    47: 0x000103060c183060,
    48: 0x001e23252931211e,
    49: 0x001f040404040604,
    50: 0x003f02040810211e,
    53: 0x001e2120201f013f,
    58: 0x000c0c00000c0c00,
    59: 0x060c0c00000c0c00,
    62: 0x00060c1830180c06,
    63: 0x000c000c1830331e,
    65: 0x002121213f21211e,
    67: 0x001e21010101211e,
    68: 0x001f21212121211f,
    69: 0x003f01011f01013f,
    72: 0x002121213f212121,
    73: 0x001f04040404041f,
    77: 0x00414141495d7763,
    78: 0x0021213129252321,
    79: 0x003e41414141413e,
    81: 0x002e19312921211e,
    83: 0x001e21201e01211e,
    84: 0x000404040404041f,
    90: 0x003f01020c10203f,
    92: 0x00406030180c0603,
    95: 0x00ff000000000000,
    97: 0x003e213e201e0000,
    99: 0x001e0101011e0000,
    100: 0x003e2121213e2020,
    101: 0x003e013f211e0000,
    102: 0x000202021f02021c,
    103: 0x1e203e21213e0000,
    104: 0x00212121211f0101,
    105: 0x0004040406000400,
    107: 0x0011090709110101,
    108: 0x000e040404040406,
    109: 0x0041494949370000,
    110: 0x00212121211f0000,
    111: 0x001e2121211e0000,
    112: 0x02023e42423e0000,
    114: 0x00020202261a0000,
    115: 0x001f201e013e0000,
    116: 0x00180404041f0404,
    117: 0x003e212121210000,
    118: 0x000c122121210000,
    119: 0x0036494949410000,
    120: 0x0021120c12210000,
    121: 0x1e203e2121210000,
    80: 0x000101011f21211f,
    98: 0x001f2121211f0101,
}
ZEAL_ORIGIN = (8, 0)

MAX_LOOK_PNG_BYTES = 360 * 1024
MAX_ENVELOPE_BYTES = 512 * 1024
DEFAULT_STABLE_MS = 250.0
DEFAULT_POLL_S = 0.05
MATCH_MAX_DISTANCE = 3
CAPTION_MAX_CHARS = 240
GLYPH_CELL = 8
UNDERLINE_ROW = 0xFF << 56


class ScreenError(Exception):
    """Structured screen failure, converted to an envelope dict."""

    def __init__(self, message: str, code: str, fix: str | None = None, **fields: Any) -> None:
        super().__init__(message)
        self.code = code
        self.fields = fields
        self.envelope = {
            "ok": False,
            "error": message,
            "code": code,
            "fix": fix if fix is not None else CODE_FIX.get(code, "See docs/CONTRACTS.md."),
            **fields,
        }


@dataclass
class Runtime:
    qmp: Any = None
    serial: Any = None
    flavor: str = DEFAULT
    state_dir: Path | None = None
    last_pointer: tuple[int, int] | None = None
    type_delay_s: float = 0.09


_RUNTIME: Runtime | None = None


def bind(
    *,
    qmp: Any = None,
    serial: Any = None,
    flavor: str | None = None,
    state_dir: Path | str | None = None,
    last_pointer: tuple[int, int] | None = None,
    type_delay_s: float | None = None,
) -> Runtime:
    """Attach a QMP (and optional serial) session. Used by tests and Slice A."""
    global _RUNTIME
    current = _RUNTIME or Runtime()
    if qmp is not None:
        current.qmp = qmp
    if serial is not None:
        current.serial = serial
    if flavor is not None:
        current.flavor = str(flavor)
    if state_dir is not None:
        current.state_dir = Path(state_dir)
    if last_pointer is not None:
        current.last_pointer = last_pointer
    if type_delay_s is not None:
        current.type_delay_s = float(type_delay_s)
    _RUNTIME = current
    return current


def unbind() -> None:
    global _RUNTIME
    _RUNTIME = None


def get_runtime() -> Runtime | None:
    """Return the bound runtime, or Slice A's vm.get_runtime() if it exists."""
    if _RUNTIME is not None and _RUNTIME.qmp is not None:
        return _RUNTIME
    try:
        from templeos import vm as vm_mod
    except Exception:
        return _RUNTIME
    getter = getattr(vm_mod, "get_runtime", None) or getattr(vm_mod, "runtime", None)
    if not callable(getter):
        return _RUNTIME
    try:
        raw = getter()
    except NotImplementedError:
        return _RUNTIME
    if raw is None:
        return None
    if isinstance(raw, Runtime):
        return raw
    if isinstance(raw, dict):
        return Runtime(
            qmp=raw.get("qmp"),
            serial=raw.get("serial"),
            flavor=str(raw.get("flavor") or DEFAULT),
            state_dir=Path(raw["state_dir"]) if raw.get("state_dir") else None,
            last_pointer=raw.get("last_pointer"),
        )
    qmp = getattr(raw, "qmp", None)
    if qmp is not None:
        return Runtime(
            qmp=qmp,
            serial=getattr(raw, "serial", None),
            flavor=str(getattr(raw, "flavor", None) or DEFAULT),
            state_dir=Path(getattr(raw, "state_dir")) if getattr(raw, "state_dir", None) else None,
            last_pointer=getattr(raw, "last_pointer", None),
        )
    return _RUNTIME


def _slice_a_landed() -> bool:
    try:
        from templeos import vm as vm_mod
    except Exception:
        return False
    return callable(getattr(vm_mod, "get_runtime", None) or getattr(vm_mod, "runtime", None))


def require_runtime() -> Runtime:
    rt = get_runtime()
    if rt is not None and rt.qmp is not None:
        return rt
    if _slice_a_landed():
        raise ScreenError(
            "The TempleOS VM is not running.",
            Code.VM_NOT_RUNNING,
        )
    raise NotImplementedError(
        "templeos.screen: Slice B (feat/screen-input) requires a bound QMP runtime"
    )


def _require_pil() -> Any:
    if Image is None:
        raise ScreenError(
            "Pillow is required to decode screendumps and encode PNG frames.",
            Code.DOCTOR_FAILED,
            "Install pillow>=10,<12 (add it to the plugin's pyproject pin).",
        )
    return Image


def _resample_nearest() -> Any:
    ImageMod = _require_pil()
    resampling = getattr(ImageMod, "Resampling", ImageMod)
    return getattr(resampling, "NEAREST", ImageMod.NEAREST)


def _state_frames(rt: Runtime) -> Path:
    if rt.state_dir is not None:
        d = Path(rt.state_dir) / "frames"
        d.mkdir(parents=True, exist_ok=True)
        return d
    root = ensure_layout()
    d = frames_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    return d


def capture_image() -> Any:
    """QMP screendump to a temp PPM under the state dir, then PIL decode.

    FakeQMP may write a PNG regardless of the requested format; both are accepted.
    """
    ImageMod = _require_pil()
    rt = require_runtime()
    dest_dir = _state_frames(rt)
    tmp = dest_dir / f"screendump-{os.getpid()}-{time.time_ns()}.ppm"
    rt.qmp.screendump(tmp, fmt="ppm")
    path = tmp
    if not path.exists():
        alt = tmp.with_suffix(".png")
        if alt.exists():
            path = alt
        else:
            raise ScreenError("QMP screendump did not write a frame.", Code.VM_NOT_RUNNING)
    im = ImageMod.open(path).convert("RGB")
    last_png = dest_dir / "last.png"
    im.save(last_png, format="PNG")
    try:
        if path != tmp:
            path.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    return im


def encode_png(im: Any, *, max_bytes: int = MAX_LOOK_PNG_BYTES) -> tuple[bytes, Any]:
    """Encode PNG, downscaling with nearest-neighbour if the cap is exceeded."""
    nearest = _resample_nearest()
    work = im
    data = b""
    for scale in (1.0, 0.75, 0.5, 0.35, 0.25):
        if scale != 1.0:
            w = max(8, int(im.width * scale))
            h = max(8, int(im.height * scale))
            work = im.resize((w, h), nearest)
        buf = io.BytesIO()
        work.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data, work
    return data, work


def encode_jpeg(im: Any, *, quality: int = 85, max_bytes: int = MAX_LOOK_PNG_BYTES) -> bytes:
    nearest = _resample_nearest()
    work = im.convert("RGB")
    data = b""
    for q in (quality, 70, 50, 35):
        buf = io.BytesIO()
        work.save(buf, format="JPEG", quality=q, optimize=True)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            return data
        work = work.resize(
            (max(8, work.width // 2), max(8, work.height // 2)),
            nearest,
        )
    return data


def _clip_crop(im: Any, crop: dict[str, int] | None, flavor: str | None) -> tuple[int, int, int, int]:
    if crop is None:
        crop = flavor_hash_crop(flavor)
    x = int(crop.get("x", 0))
    y = int(crop.get("y", 0))
    w = int(crop.get("w", im.width))
    h = int(crop.get("h", im.height))
    x = max(0, min(x, im.width))
    y = max(0, min(y, im.height))
    w = max(1, min(w, im.width - x) if im.width - x else 1)
    h = max(1, min(h, im.height - y) if im.height - y else 1)
    return x, y, w, h


def hash_image(im: Any, *, crop: dict[str, int] | None = None, flavor: str | None = None) -> dict[str, Any]:
    x, y, w, h = _clip_crop(im, crop, flavor)
    region = im.crop((x, y, x + w, y + h)).convert("RGB")
    sha = hashlib.sha256(region.tobytes()).hexdigest()
    full = hashlib.sha256(im.convert("RGB").tobytes()).hexdigest()
    return {
        "ok": True,
        "sha256": sha,
        "full_sha256": full,
        "crop": {"x": x, "y": y, "w": w, "h": h},
        "width": im.width,
        "height": im.height,
    }


def _font_for(flavor: str | None) -> dict[int, int]:
    key = (flavor or DEFAULT).strip().lower() or DEFAULT
    if key == "zealos":
        return dict(ZEAL_FONT)
    return {i: STD_FONT[i] for i in range(256)}


def _glyph_origin(flavor: str | None, origin: tuple[int, int] | None) -> tuple[int, int]:
    if origin is not None:
        return origin
    key = (flavor or DEFAULT).strip().lower() or DEFAULT
    if key == "zealos":
        return ZEAL_ORIGIN
    return (0, 0)


def _cell_u64(im: Any, col: int, row: int, *, origin_x: int = 0, origin_y: int = 0) -> int:
    x0 = origin_x + col * GLYPH_CELL
    y0 = origin_y + row * GLYPH_CELL
    if x0 < 0 or y0 < 0 or x0 + GLYPH_CELL > im.width or y0 + GLYPH_CELL > im.height:
        return 0
    pixels: list[tuple[int, int, int]] = []
    for dy in range(GLYPH_CELL):
        for dx in range(GLYPH_CELL):
            pix = im.getpixel((x0 + dx, y0 + dy))
            if not isinstance(pix, tuple):
                pix = (int(pix), int(pix), int(pix))
            else:
                pix = (int(pix[0]), int(pix[1]), int(pix[2]))
            pixels.append(pix)
    bg = Counter(pixels).most_common(1)[0][0]
    value = 0
    for dy in range(GLYPH_CELL):
        byte = 0
        for dx in range(GLYPH_CELL):
            if pixels[dy * GLYPH_CELL + dx] != bg:
                byte |= 1 << dx
        value |= byte << (8 * dy)
    return value


def _variants(value: int) -> list[int]:
    mask = (1 << 64) - 1
    out = [value & mask, (~value) & mask]
    extra: list[int] = []
    for v in list(out):
        if ((v >> 56) & 0xFF) == 0xFF:
            extra.append(v & ((1 << 56) - 1))
    out.extend(extra)
    return out


def _hamming(a: int, b: int) -> int:
    return bin((a ^ b) & ((1 << 64) - 1)).count("1")


def _match_cell(value: int, font: dict[int, int]) -> tuple[int, int]:
    """Return (codepoint, hamming). Space for an empty cell."""
    if value == 0:
        return 32, 0
    best_d = 65
    best_i = 32
    for variant in _variants(value):
        for idx, glyph in font.items():
            d = min(_hamming(variant, glyph), _hamming(variant, glyph | UNDERLINE_ROW))
            ascii_pref = 32 <= idx < 127
            best_ascii = 32 <= best_i < 127
            if d < best_d or (d == best_d and ascii_pref and not best_ascii):
                best_d = d
                best_i = idx
                if d == 0 and ascii_pref:
                    return best_i, best_d
    return best_i, best_d


def glyph_read_ex(
    image: Any,
    *,
    flavor: str | None = None,
    origin: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Match official 8x8 glyphs. Returns text, rows, and a confidence score."""
    ImageMod = _require_pil()
    if not hasattr(image, "size"):
        raise TypeError("glyph_read_ex expects a PIL image")
    im = image.convert("RGB")
    ox, oy = _glyph_origin(flavor, origin)
    cols = (im.width - ox) // GLYPH_CELL
    rows_n = (im.height - oy) // GLYPH_CELL
    font = _font_for(flavor)
    rows: list[str] = []
    scored = 0
    matched = 0
    exact = 0
    distance_sum = 0
    for row in range(max(0, rows_n)):
        chars: list[str] = []
        for col in range(max(0, cols)):
            value = _cell_u64(im, col, row, origin_x=ox, origin_y=oy)
            if value == 0:
                chars.append(" ")
                continue
            scored += 1
            idx, dist = _match_cell(value, font)
            if dist <= MATCH_MAX_DISTANCE and 32 <= idx < 127:
                chars.append(chr(idx))
                matched += 1
                distance_sum += dist
                if dist == 0:
                    exact += 1
            elif dist <= MATCH_MAX_DISTANCE:
                chars.append(" ")
                matched += 1
                distance_sum += dist
            else:
                chars.append(" ")
        rows.append("".join(chars).rstrip())
    while rows and not rows[-1].strip():
        rows.pop()
    text = "\n".join(rows)
    confidence = (matched / scored) if scored else 1.0
    return {
        "ok": True,
        "text": text,
        "rows": rows,
        "confidence": round(confidence, 4),
        "cells": scored,
        "matched": matched,
        "exact": exact,
        "mean_distance": (round(distance_sum / matched, 4) if matched else 0.0),
        "source": "glyphs",
        "width": im.width,
        "height": im.height,
        "origin": {"x": ox, "y": oy},
    }


def glyph_read(image: Path | bytes, *, flavor: str | None = None, origin: tuple[int, int] | None = None) -> str:
    """Match official 8x8 glyphs on a screendump. Used when serial is silent."""
    # Empty bytes stay NotImplemented so Slice 0's stub test keeps passing
    # until integration drops that assertion. Real frames use the matcher.
    if isinstance(image, (bytes, bytearray, memoryview)) and not bytes(image):
        raise NotImplementedError("templeos.screen.glyph_read: Slice B (feat/screen-input)")
    ImageMod = _require_pil()
    if isinstance(image, (bytes, bytearray, memoryview)):
        im = ImageMod.open(io.BytesIO(bytes(image))).convert("RGB")
    else:
        im = ImageMod.open(image).convert("RGB")
    return str(glyph_read_ex(im, flavor=flavor, origin=origin)["text"])


def _caption_from(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    useful = [ln for ln in lines if any(ch.isalpha() for ch in ln)]
    boost = (
        "Hello",
        "T:/",
        "Help",
        "Cmd",
        "TempleOS",
        "TinkerOS",
        "ZealOS",
        "Overview",
        "Public Domain",
        "HolyC",
        "Directory",
    )
    chrome = ("FPS:", "MENU ", "SHIFT", " CPU ", "ENTER")

    def score(line: str) -> int:
        s = 1
        for token in boost:
            if token in line:
                s += 8
        low = line
        if any(tok in low for tok in chrome):
            s -= 6
        if ":" in line and "/" in line and any(ch.isdigit() for ch in line):
            s -= 3  # clock / date chrome
        return s

    ranked = sorted(useful, key=score, reverse=True)
    chosen = [ln for ln in ranked if score(ln) > 0][:5] or useful[:4] or lines[:4]
    # Prefer keeping document order among the chosen lines.
    chosen.sort(key=lambda ln: next((i for i, orig in enumerate(useful) if orig == ln), 0))
    caption = " | ".join(chosen)
    caption = " ".join(caption.split())
    if len(caption) > CAPTION_MAX_CHARS:
        caption = caption[: CAPTION_MAX_CHARS - 1] + "…"
    return caption or "(blank frame)"



def look(*, dest: Path | None = None) -> dict[str, Any]:
    """Return a PNG frame: width, height, mime, sha256, data (base64), caption.

    Budget the whole serialized JSON (base64 included) under the 512 KiB
    pane relay limit and fail with payload_too_large rather than truncate.
    """
    try:
        im = capture_image()
    except ScreenError as exc:
        return exc.envelope
    if dest is not None:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, format="PNG")
    try:
        data, out = encode_png(im)
    except ScreenError as exc:
        return exc.envelope
    encoded = base64.b64encode(data).decode("ascii")
    sha = hashlib.sha256(data).hexdigest()
    flavor = DEFAULT
    try:
        flavor = require_runtime().flavor
    except (NotImplementedError, ScreenError):
        pass
    try:
        ocr = glyph_read_ex(im, flavor=flavor)
        caption = _caption_from(str(ocr.get("text") or ""))
        crop_info = hash_image(im, flavor=flavor)
    except Exception:
        ocr = {}
        caption = f"{out.width}x{out.height} PNG"
        crop_info = {}
    body: dict[str, Any] = {
        "ok": True,
        "mime": "image/png",
        "width": out.width,
        "height": out.height,
        "data": encoded,
        "sha256": sha,
        "caption": caption,
        "crop_sha256": crop_info.get("sha256"),
        "text_confidence": ocr.get("confidence"),
    }
    packed = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if len(packed.encode("utf-8")) > MAX_ENVELOPE_BYTES:
        return {
            "ok": False,
            "error": "Look frame exceeded the 512 KiB JSON relay budget.",
            "code": Code.PAYLOAD_TOO_LARGE,
            "fix": CODE_FIX[Code.PAYLOAD_TOO_LARGE],
            "mime": "image/png",
            "width": out.width,
            "height": out.height,
            "sha256": sha,
            "data": None,
        }
    return body


def read_text() -> dict[str, Any]:
    """Return {text, source} where source is serial or glyphs."""
    try:
        rt = require_runtime()
    except ScreenError as exc:
        return exc.envelope
    serial = rt.serial
    if serial is not None and getattr(serial, "connected", False):
        try:
            raw = serial.read_available()
        except Exception:
            raw = b""
        if raw:
            text = raw.decode("utf-8", "replace").replace("\x00", "")
            rows = text.splitlines()
            return {
                "ok": True,
                "text": text,
                "rows": rows,
                "source": "serial",
                "confidence": 1.0,
            }
    try:
        im = capture_image()
        result = glyph_read_ex(im, flavor=rt.flavor)
        result["source"] = "glyphs"
        return result
    except ScreenError as exc:
        return exc.envelope


def wait_idle(
    *,
    timeout_s: float = 5.0,
    crop: dict[str, int] | None = None,
    stable_ms: float = DEFAULT_STABLE_MS,
) -> dict[str, Any]:
    """Wait until the cropped frame hash is stable, or time out."""
    if timeout_s < 0:
        raise ValueError("timeout_s must be >= 0")
    started = time.monotonic()
    deadline = started + float(timeout_s)
    last: str | None = None
    stable_since: float | None = None
    poll = min(DEFAULT_POLL_S, max(0.01, float(stable_ms) / 2000.0))
    info: dict[str, Any] = {}
    while True:
        try:
            im = capture_image()
            flavor = require_runtime().flavor
            info = hash_image(im, crop=crop, flavor=flavor)
        except ScreenError as exc:
            return exc.envelope
        sha = str(info["sha256"])
        now = time.monotonic()
        if sha == last:
            if stable_since is None:
                stable_since = now
            if (now - stable_since) * 1000.0 >= float(stable_ms):
                return {
                    "ok": True,
                    "sha256": sha,
                    "crop": info.get("crop"),
                    "waited_s": round(now - started, 4),
                    "stable_ms": float(stable_ms),
                }
        else:
            last = sha
            stable_since = now
        if now >= deadline:
            return {
                "ok": False,
                "error": f"Frame did not stay idle for {stable_ms} ms within {timeout_s} s.",
                "code": Code.TIMEOUT,
                "fix": CODE_FIX[Code.TIMEOUT],
                "sha256": sha,
                "crop": info.get("crop"),
                "waited_s": round(now - started, 4),
            }
        remaining = deadline - now
        time.sleep(min(poll, max(0.0, remaining)))


def frame_hash(*, crop: dict[str, int] | None = None) -> dict[str, Any]:
    """SHA-256 of the cropped framebuffer (not the chrome clock)."""
    try:
        im = capture_image()
        flavor = require_runtime().flavor
        return hash_image(im, crop=crop, flavor=flavor)
    except ScreenError as exc:
        return exc.envelope
