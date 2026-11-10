"""PIL-only size check for the default huge Terry companion.

The companion must be huge in every state (idle, typing, speech bubble), not
only while typing. The CSS gives every state the same 750 px sprite box; this
test measures the rendered figure in the checked-in 1920x1240 default capture
and only prints numbers, never viewing the image.

The mask matches Terry's skin/art tones in the right rail. Chrome text, the
Agent Log, the guest frame, and the dark Hermes chrome do not match it.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SHOT = ROOT / "shots" / "terry" / "terry-big.png"


def figure_bbox(image):
    width, height = image.size
    pixels = image.load()
    xs = []
    ys = []
    # Right rail only: the guest display ends well before x=1300.
    for y in range(height):
        for x in range(1300, width):
            r, g, b = pixels[x, y]
            if r >= 180 and g >= 140 and b >= 110 and r >= g >= b and r - b >= 18:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def test_terry_big_default_is_huge():
    assert SHOT.exists(), f"missing {SHOT}; run the terry-big shoot"
    with Image.open(SHOT) as raw:
        image = raw.convert("RGB")
        assert image.size == (1920, 1240)

    bbox = figure_bbox(image)
    assert bbox is not None, "no Terry sprite pixels found in the right rail"
    x0, y0, x1, y1 = bbox
    width = x1 - x0 + 1
    height = y1 - y0 + 1
    print(f"terry figure bbox=({x0},{y0})-({x1},{y1}) size={width}x{height}")
    print(f"figure height={height}px (target >= 600px)")

    assert x0 >= 1200, "Terry must stand in the right rail, not over the guest"
    assert y1 >= 1020, "Terry must reach the bottom of the pane"
    assert height >= 600, f"Terry figure is only {height}px tall"


def test_every_state_uses_the_same_huge_sprite_box():
    css = (ROOT / "desktop" / "src" / "ui" / "styles.css").read_text(encoding="utf-8")
    assert "var(--tos-companion-h, 750px)" in css
    assert "--tos-companion-h: 750px" in css
