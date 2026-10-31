"""Writes the app icon: Ishara's four-bar mark on its purple gradient, 1024×1024, full bleed.

    uv run --with pillow python scripts/make_app_icon.py

iOS rounds the corners itself, so the square has none. The colours and proportions match
the mark everywhere else (README diagrams): a 150° gradient from #A56BFF through #8B3DFF
(55%) to #6A1FE0, and four white bars 10% wide with 7% gaps, 46/70/62/38% tall.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE, SCALE = 1024, 4
OUT = Path(__file__).resolve().parent.parent / "ios/Ishara/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png"
STOPS = [(0.0, (0xA5, 0x6B, 0xFF)), (0.55, (0x8B, 0x3D, 0xFF)), (1.0, (0x6A, 0x1F, 0xE0))]


def gradient(size: int) -> Image.Image:
    """CSS linear-gradient(150deg, …) over a square."""
    angle = math.radians(150)
    dx, dy = math.sin(angle), -math.cos(angle)
    length = size * (abs(dx) + abs(dy))
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = ((x - size / 2) * dx + (y - size / 2) * dy) / length + 0.5
            t = min(1.0, max(0.0, t))
            for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
                if t <= t1:
                    u = (t - t0) / (t1 - t0)
                    px[x, y] = tuple(round(a + (b - a) * u) for a, b in zip(c0, c1))
                    break
    return img


def main() -> None:
    big = SIZE * SCALE
    img = gradient(SIZE).resize((big, big), Image.BICUBIC)
    draw = ImageDraw.Draw(img)
    width, gap = 0.10 * big, 0.07 * big
    left = big / 2 - (4 * width + 3 * gap) / 2
    for i, h in enumerate([0.46, 0.70, 0.62, 0.38]):
        x0 = left + i * (width + gap)
        y0 = big / 2 - h * big / 2
        draw.rounded_rectangle([x0, y0, x0 + width, y0 + h * big], radius=width / 2, fill=(255, 255, 255))
    img.resize((SIZE, SIZE), Image.LANCZOS).save(OUT, optimize=True)
    print(f"wrote {OUT.relative_to(OUT.parents[5])}")


if __name__ == "__main__":
    main()
