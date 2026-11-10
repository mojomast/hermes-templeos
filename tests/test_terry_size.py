"""PIL-only size and sharpness checks for the huge Terry companion.

The v4 rig must render at native high resolution at the TERRY-BIG default size.
These tests measure the checked-in 1920x1240 captures and only print numbers;
they never view the images. Flat colour fills in the art are allowed, but the
figure must not be a 3x nearest-neighbour upscale of a ~1/3-resolution image.
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parents[1]
SHOT = ROOT / "shots" / "terry" / "terry-big.png"
V4_DIR = ROOT / "shots" / "terry"
V4_SHOTS = (
    V4_DIR / "v4-idle.png",
    V4_DIR / "v4-typing.png",
    V4_DIR / "v4-talking.png",
    V4_DIR / "v4-costume.png",
)


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


def v4_figure_bbox(image):
    """Whole-figure bbox in the right rail, including hat and costume.

    Starts below the Agent Log and speech bubble so their bright text cannot
    become the figure crown. The threshold accepts skin, the white cap/hat,
    and costume cloth while rejecting the dark Hermes rail.
    """
    width, height = image.size
    pixels = image.load()
    xs = []
    ys = []
    for y in range(450, height):
        for x in range(1300, width):
            r, g, b = pixels[x, y]
            bright = max(r, g, b)
            chroma = bright - min(r, g, b)
            if bright >= 110 and (chroma >= 12 or bright >= 180):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def nearest_neighbor_residual(image):
    """Mean residual against NN-upscale(NN-downscale(figure, 3), 3).

    A 3x nearest-neighbour figure reproduces itself exactly and scores 0.
    Real high-resolution art leaves a nonzero residual on edges. Returns
    (mean_all, mean_edge, flat_edge_fraction).
    """
    width, height = image.size
    small = image.resize((max(1, width // 3), max(1, height // 3)), Image.NEAREST)
    upscaled = small.resize((width, height), Image.NEAREST)
    gray = image.convert("L")
    up_gray = upscaled.convert("L")
    diff = ImageChops.difference(gray, up_gray)
    mean_all = float(ImageStat.Stat(diff).mean[0])

    edge = gray.filter(ImageFilter.FIND_EDGES).point(lambda value: 255 if value > 30 else 0)
    masked = Image.composite(diff, Image.new("L", (width, height), 0), edge)
    mean_edge = float(ImageStat.Stat(masked).mean[0])

    gray_px = gray.load()
    edge_px = edge.load()
    flat = 0
    edges = 0
    for y in range(2, height):
        for x in range(2, width):
            if not edge_px[x, y]:
                continue
            edges += 1
            value = gray_px[x, y]
            if (
                value == gray_px[x - 1, y]
                == gray_px[x - 2, y]
                == gray_px[x, y - 1]
                == gray_px[x, y - 2]
            ):
                flat += 1
    flat_fraction = flat / max(1, edges)
    return mean_all, mean_edge, flat_fraction


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


def test_v4_shots_are_huge_in_every_state():
    for shot in V4_SHOTS:
        assert shot.exists(), f"missing {shot}; run the v4 Terry shoot"
        with Image.open(shot) as raw:
            image = raw.convert("RGB")
            assert image.size == (1920, 1240), f"{shot.name} is not 1920x1240"
        bbox = v4_figure_bbox(image)
        assert bbox is not None, f"no Terry v4 figure pixels in {shot.name}"
        x0, y0, x1, y1 = bbox
        width = x1 - x0 + 1
        height = y1 - y0 + 1
        print(f"{shot.name}: bbox=({x0},{y0})-({x1},{y1}) size={width}x{height} height={height}px")
        assert x0 >= 1300, f"{shot.name}: Terry must stay in the right rail"
        assert y1 >= 1020, f"{shot.name}: Terry must reach the bottom of the pane"
        assert height >= 600, f"{shot.name}: Terry figure is only {height}px tall"


def test_v4_is_not_a_nearest_neighbor_upscale():
    for shot in V4_SHOTS:
        with Image.open(shot) as raw:
            image = raw.convert("RGB")
        bbox = v4_figure_bbox(image)
        assert bbox is not None
        x0, y0, x1, y1 = bbox
        figure = image.crop((x0, y0, x1 + 1, y1 + 1))
        mean_all, mean_edge, flat_fraction = nearest_neighbor_residual(figure)
        print(
            f"{shot.name}: nn_residual_all={mean_all:.3f} "
            f"nn_residual_edges={mean_edge:.3f} flat_edge_fraction={flat_fraction:.3f}"
        )
        assert mean_all > 0.5, f"{shot.name}: figure looks like a flat NN upscale"
        assert mean_edge > 0.75, f"{shot.name}: edges carry no real high-res detail"
        assert flat_fraction < 0.25, f"{shot.name}: figure has a regular duplicated-pixel grid"


PINT2_SHOTS = (
    V4_DIR / "pint2-idle.png",
    V4_DIR / "pint2-typing.png",
)


def test_pint2_shots_are_huge_and_sharp():
    for shot in PINT2_SHOTS:
        assert shot.exists(), f"missing {shot}; run shoot_pane for pint2 idle/typing"
        with Image.open(shot) as raw:
            image = raw.convert("RGB")
            assert image.size == (1920, 1240), f"{shot.name} is not 1920x1240"
        bbox = v4_figure_bbox(image)
        assert bbox is not None, f"no Terry figure pixels in {shot.name}"
        x0, y0, x1, y1 = bbox
        width = x1 - x0 + 1
        height = y1 - y0 + 1
        print(f"{shot.name}: bbox=({x0},{y0})-({x1},{y1}) size={width}x{height} height={height}px")
        assert x0 >= 1300, f"{shot.name}: Terry must stay in the right rail"
        assert y1 >= 1020, f"{shot.name}: Terry must reach the bottom of the pane"
        assert height >= 600, f"{shot.name}: Terry figure is only {height}px tall"
        figure = image.crop((x0, y0, x1 + 1, y1 + 1))
        mean_all, mean_edge, flat_fraction = nearest_neighbor_residual(figure)
        print(
            f"{shot.name}: nn_residual_all={mean_all:.3f} "
            f"nn_residual_edges={mean_edge:.3f} flat_edge_fraction={flat_fraction:.3f}"
        )
        assert mean_all > 0.5, f"{shot.name}: figure looks like a flat NN upscale"
        assert mean_edge > 0.75, f"{shot.name}: edges carry no real high-res detail"
        assert flat_fraction < 0.25, f"{shot.name}: figure has a regular duplicated-pixel grid"
