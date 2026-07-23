"""Generate the integration icon assets.

Produces `icon.png` (256x256) and `icon@2x.png` (512x512) with a rounded-square
energy-themed background and a white lightning bolt. Rendered at 4x and
downsampled for smooth anti-aliasing.

Home Assistant 2026.3+ serves these directly from the integration's local
``brand/`` directory (they take precedence over the home-assistant/brands
repository), so the output goes to
``custom_components/ecoflow_streamx/brand/``. Run from the repo root:

    python3 scripts/generate_icon.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

# Repo root is the parent of this script's ``scripts/`` directory.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(
    _ROOT, "custom_components", "ecoflow_streamx", "brand"
)

# Supersample factor for anti-aliasing.
SS = 4
BASE = 256

# Gradient (top -> bottom): teal to blue, an "energy" feel.
TOP = (43, 217, 196)   # #2BD9C4
BOTTOM = (22, 103, 214)  # #1667D6
BOLT = (255, 255, 255)

# Lightning bolt polygon on a normalised 0..1 grid (x right, y down).
BOLT_POINTS = [
    (0.56, 0.08),
    (0.30, 0.52),
    (0.47, 0.52),
    (0.42, 0.92),
    (0.72, 0.44),
    (0.54, 0.44),
    (0.62, 0.08),
]


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _gradient(size: int) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        r = round(TOP[0] + (BOTTOM[0] - TOP[0]) * t)
        g = round(TOP[1] + (BOTTOM[1] - TOP[1]) * t)
        b = round(TOP[2] + (BOTTOM[2] - TOP[2]) * t)
        grad.putpixel((0, y), (r, g, b))
    return grad.resize((size, size))


def build(size: int) -> Image.Image:
    s = size * SS
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # Rounded-square gradient background.
    bg = _gradient(s).convert("RGBA")
    mask = _rounded_mask(s, radius=int(s * 0.22))
    canvas.paste(bg, (0, 0), mask)

    # Lightning bolt.
    pts = [(x * s, y * s) for (x, y) in BOLT_POINTS]
    draw = ImageDraw.Draw(canvas)
    draw.polygon(pts, fill=BOLT)

    return canvas.resize((size, size), Image.LANCZOS)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    build(BASE).save(os.path.join(OUT_DIR, "icon.png"), optimize=True)
    build(BASE * 2).save(os.path.join(OUT_DIR, "icon@2x.png"), optimize=True)
    print(f"Wrote icon.png (256) and icon@2x.png (512) to {OUT_DIR}")


if __name__ == "__main__":
    main()
