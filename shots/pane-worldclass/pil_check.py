"""PIL-only geometry checks for the pane-worldclass shots.

Reads the layout rectangles measured by desktop/shoot_pane.mjs, then verifies
with PIL that each region actually contains pixels, that content stays inside
its measured box, that the screen/log/Terry boxes do not overlap, and that the
speech bubble is fully contained by Terry's column. Never displays an image.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RECTS = json.loads((HERE / "PANE-RECTS.json").read_text(encoding="utf-8"))
EXPECTED = {
    "pane-1920x1240.png": (1920, 1240),
    "pane-1280x800.png": (1280, 800),
    "pane-narrow.png": (820, 1080),
}


def mask_bbox(image: Image.Image, box, predicate):
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(image.width, x1)
    y1 = min(image.height, y1)
    crop = image.crop((x0, y0, x1, y1))
    pixels = crop.load()
    xs = []
    ys = []
    for y in range(crop.height):
        for x in range(crop.width):
            if predicate(pixels[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (x0 + min(xs), y0 + min(ys), x0 + max(xs), y0 + max(ys))


def box(rect):
    return (rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"])


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def inside(inner, outer, tolerance=1):
    return (
        inner[0] >= outer[0] - tolerance
        and inner[1] >= outer[1] - tolerance
        and inner[2] <= outer[2] + tolerance
        and inner[3] <= outer[3] + tolerance
    )


def fmt(b):
    return f"({b[0]:.1f},{b[1]:.1f})-({b[2]:.1f},{b[3]:.1f})"


def content_bbox(image, rect, kind):
    if kind == "screen":
        return mask_bbox(image, box(rect), lambda p: max(p) >= 170)
    if kind == "bubble":
        return mask_bbox(image, box(rect), lambda p: p[0] >= 170 and p[1] >= 150 and p[2] <= 180)
    return mask_bbox(
        image,
        box(rect),
        lambda p: max(p) >= 110 and (max(p) - min(p) >= 12 or max(p) >= 180),
    )


def main():
    lines = ["PIL bbox checks (PIL only; no image is displayed or read in-model)", ""]
    ok = True
    for name, expected in EXPECTED.items():
        rects = RECTS.get(name)
        lines.append(f"{name}:")
        if not rects:
            lines.append("  FAIL missing PANE-RECTS entry")
            ok = False
            continue
        path = HERE / name
        with Image.open(path) as raw:
            image = raw.convert("RGB")
        if image.size != expected:
            lines.append(f"  FAIL size {image.size} != {expected}")
            ok = False
        boxes = {}
        for region in ("screen", "log", "terry", "bubble"):
            rect = rects.get(region)
            if not rect:
                lines.append(f"  {region}: MISSING")
                boxes[region] = None
                if region != "bubble":
                    ok = False
                continue
            boxes[region] = box(rect)
            lines.append(
                f"  {region} rect {fmt(boxes[region])} size={rect['width']:.1f}x{rect['height']:.1f}"
            )
            content = content_bbox(image, rect, region)
            if content is None:
                lines.append(f"  {region} content: NONE")
                ok = False
            else:
                lines.append(f"  {region} content bbox {fmt(content)}")
                if not inside(content, boxes[region]):
                    lines.append(f"  FAIL {region} content escapes its rect")
                    ok = False
        if all(boxes.get(region) for region in ("screen", "log", "terry")):
            pairs = [
                ("screen", "log"),
                ("screen", "terry"),
                ("log", "terry"),
            ]
            for left, right in pairs:
                hit = overlap(boxes[left], boxes[right])
                lines.append(f"  overlap {left}/{right}: {'FAIL' if hit else 'none'}")
                ok = ok and not hit
            same_width = abs(boxes["screen"][2] - boxes["screen"][0] - (boxes["log"][2] - boxes["log"][0]))
            lines.append(f"  screen/log width delta: {same_width:.1f}px")
            ok = ok and same_width <= 1.0
            log_below = boxes["log"][1] >= boxes["screen"][3]
            lines.append(f"  log below screen: {'yes' if log_below else 'FAIL'}")
            ok = ok and log_below
        if boxes.get("bubble") and boxes.get("terry"):
            contained = inside(boxes["bubble"], boxes["terry"])
            lines.append(f"  bubble inside Terry column: {'yes' if contained else 'FAIL'}")
            ok = ok and contained
        lines.append(f"  RESULT: {'PASS' if ok else 'FAIL'}")
        lines.append("")
    lines.append(f"OVERALL: {'PASS' if ok else 'FAIL'}")
    text = "\n".join(lines) + "\n"
    (HERE / "PIL-CHECKS.txt").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
