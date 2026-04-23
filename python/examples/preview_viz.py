"""Showcase every viz primitive on a single 800x480 panel.

Run:
    uv run python examples/preview_viz.py
Outputs:
    /tmp/reterminal-review/viz-showcase.png
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from reterminal.render.viz import (
    dots,
    heatmap,
    progress_bar,
    ring,
    scale,
    shape,
    sparkline,
)

WIDTH, HEIGHT = 800, 480
OUT = Path("/tmp/reterminal-review/viz-showcase.png")
HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    if not HELVETICA.exists():
        return ImageFont.load_default()
    return ImageFont.truetype(str(HELVETICA), size, index={"regular": 0, "bold": 1}[weight])


def label(draw: ImageDraw.ImageDraw, text: str, x: int, y: int) -> None:
    draw.text((x, y), text, font=font(12, "bold"), fill=0)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)

    draw.text((24, 18), "VIZ RUBRIC", font=font(14, "bold"), fill=0)
    draw.text((24, 34), "reterminal.render.viz primitives, rendered on-panel", font=font(12), fill=0)

    col1_x, col2_x = 24, 420
    row_y = 70

    # --- progress_bar: segmented
    label(draw, "progress_bar — segmented (2 of 4)", col1_x, row_y)
    progress_bar(draw, col1_x, row_y + 20, 340, 14, value=2, total=4, segments=4, gap=4)

    # --- progress_bar: continuous
    label(draw, "progress_bar — continuous (47%)", col2_x, row_y)
    progress_bar(draw, col2_x, row_y + 20, 340, 14, value=47, total=100)

    row_y += 60

    # --- sparkline
    label(draw, "sparkline — 14-day trend", col1_x, row_y)
    random.seed(42)
    values = [random.randint(1, 10) for _ in range(14)]
    sparkline(draw, col1_x, row_y + 20, 340, 32, values)

    # --- ring
    label(draw, "ring — 65% single metric", col2_x, row_y)
    ring(draw, col2_x + 40, row_y + 44, radius=20, pct=0.65)

    row_y += 80

    # --- heatmap: 30-day
    label(draw, "heatmap — 30 days (streak-style)", col1_x, row_y)
    streak = [1, 1, 1, 1, 0, 1, 1,  # week 1
              1, 1, 1, 0, 1, 1, 1,  # week 2
              1, 1, 1, 1, 1, 1, 0,  # week 3
              1, 1, 1, 1, 1, 1, 1, 1, 1]  # week 4+
    heatmap(draw, col1_x, row_y + 20, streak, cols=7, cell=20, gap=3)

    # --- dots
    label(draw, "dots — 3 of 5", col2_x, row_y)
    dots(draw, col2_x, row_y + 22, filled=3, total=5, size=14, gap=8)

    # --- scale
    label(draw, "scale — value in range", col2_x, row_y + 62)
    scale(draw, col2_x, row_y + 94, 320, value=7, low=0, high=12, ticks=7)

    row_y += 140

    # --- shapes row
    label(draw, "shape — category glyphs (circle / square / triangle / diamond / star / outline)", col1_x, row_y)
    kinds = ["circle", "square", "triangle", "diamond", "star", "triangle_outline"]
    for i, k in enumerate(kinds):
        shape(draw, col1_x + 20 + i * 48, row_y + 36, k, size=24)
        draw.text((col1_x + 4 + i * 48, row_y + 56), k[:7], font=font(10), fill=0)

    # Footer
    draw.text(
        (24, HEIGHT - 22),
        "see docs/visualizations.md for when to use each primitive",
        font=font(10),
        fill=0,
    )

    final = img.point(lambda x: 255 if x >= 192 else 0, mode="1")
    final.save(OUT)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
