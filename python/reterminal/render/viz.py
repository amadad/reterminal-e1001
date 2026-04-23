"""1-bit visualization primitives for the monochrome ePaper display.

Inspired by Chartli's visual vocabulary (block bars, sparklines, heatmaps,
braille) but rendered with PIL directly so we do not depend on font glyph
coverage and can tune pixel-precise.

See docs/visualizations.md for the rubric — what each primitive is for,
when to use it, and when not to.

All primitives take a PIL ImageDraw and draw in place. They use `fill=0`
(black) by default for on-pixels; the caller owns the canvas orientation
and background.
"""

from __future__ import annotations

import math
from typing import Sequence

from PIL import ImageDraw


# ---------------------------------------------------------------------------
# Progress bar: bounded progress toward a known total.
# ---------------------------------------------------------------------------


def progress_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    height: int,
    value: float,
    total: float,
    *,
    segments: int | None = None,
    gap: int = 2,
) -> None:
    """Horizontal progress bar.

    If `segments` is given, renders as discrete filled segments with gaps
    (good for "N of M weeks" where segments feel step-wise). Otherwise
    renders as a single bar filled proportionally.
    """
    if total <= 0:
        return
    pct = max(0.0, min(1.0, value / total))

    if segments:
        seg_w = (width - gap * (segments - 1)) / segments
        filled = round(pct * segments)
        for i in range(segments):
            sx = x + i * (seg_w + gap)
            if i < filled:
                draw.rectangle([sx, y, sx + seg_w, y + height], fill=0)
            else:
                draw.rectangle([sx, y, sx + seg_w, y + height], outline=0, width=1)
    else:
        draw.rectangle([x, y, x + width, y + height], outline=0, width=1)
        inner = int(pct * (width - 2))
        if inner > 0:
            draw.rectangle([x + 1, y + 1, x + 1 + inner, y + height - 1], fill=0)


# ---------------------------------------------------------------------------
# Sparkline: trend over time as compact columns.
# ---------------------------------------------------------------------------


def sparkline(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    height: int,
    values: Sequence[float],
    *,
    gap: int = 1,
) -> None:
    """Vertical-column sparkline. Columns scale to max(values)."""
    if not values:
        return
    vmax = max(values) or 1
    n = len(values)
    col_w = (width - gap * (n - 1)) / n
    for i, v in enumerate(values):
        h = max(1, round((v / vmax) * height))
        cx = x + i * (col_w + gap)
        draw.rectangle([cx, y + height - h, cx + col_w, y + height], fill=0)


# ---------------------------------------------------------------------------
# Heatmap: 2D grid of filled/empty cells. GitHub-contributions style.
# ---------------------------------------------------------------------------


def heatmap(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    values: Sequence[float],
    *,
    cols: int,
    cell: int = 12,
    gap: int = 2,
    threshold: float = 0.5,
) -> None:
    """Grid of filled/empty cells laid out row-major.

    Each value above `threshold` renders filled; at/below renders empty box.
    Good for streak visualization (last 30 days of a habit), attendance,
    daily completion.
    """
    for i, v in enumerate(values):
        row = i // cols
        col = i % cols
        cx = x + col * (cell + gap)
        cy = y + row * (cell + gap)
        if v > threshold:
            draw.rectangle([cx, cy, cx + cell, cy + cell], fill=0)
        else:
            draw.rectangle([cx, cy, cx + cell, cy + cell], outline=0, width=1)


# ---------------------------------------------------------------------------
# Dots: small filled circles for counting. N of M.
# ---------------------------------------------------------------------------


def dots(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    filled: int,
    total: int,
    *,
    size: int = 10,
    gap: int = 4,
) -> None:
    """Row of circles — filled for `filled`, outlined for remaining."""
    r = size // 2
    for i in range(total):
        cx = x + r + i * (size + gap)
        cy = y + r
        if i < filled:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
        else:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=0, width=1)


# ---------------------------------------------------------------------------
# Ring: filled arc showing percentage. Single-metric glance.
# ---------------------------------------------------------------------------


def ring(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    radius: int,
    pct: float,
    *,
    thickness: int = 6,
) -> None:
    """Filled arc representing a 0..1 fraction. Clockwise from 12 o'clock."""
    pct = max(0.0, min(1.0, pct))
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    draw.arc(bbox, start=0, end=360, fill=0, width=1)
    if pct <= 0:
        return
    end_angle = -90 + pct * 360
    for w in range(thickness):
        inset = [
            cx - radius + w,
            cy - radius + w,
            cx + radius - w,
            cy + radius - w,
        ]
        draw.arc(inset, start=-90, end=end_angle, fill=0, width=1)


# ---------------------------------------------------------------------------
# Scale: tick-marked horizontal line with a position marker.
# ---------------------------------------------------------------------------


def scale(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    value: float,
    low: float,
    high: float,
    *,
    ticks: int = 5,
    tick_h: int = 6,
    marker_r: int = 4,
) -> None:
    """Horizontal scale with ticks and a filled marker at `value`."""
    if high <= low:
        return
    pct = max(0.0, min(1.0, (value - low) / (high - low)))
    draw.line([(x, y), (x + width, y)], fill=0, width=1)
    for i in range(ticks):
        tx = x + round(i * width / (ticks - 1))
        draw.line([(tx, y - tick_h // 2), (tx, y + tick_h // 2)], fill=0, width=1)
    mx = x + round(pct * width)
    draw.ellipse(
        [mx - marker_r, y - marker_r, mx + marker_r, y + marker_r], fill=0
    )


# ---------------------------------------------------------------------------
# Category shape: small filled glyphs for categorical labels.
# ---------------------------------------------------------------------------


SHAPE_KINDS = (
    "circle",
    "square",
    "triangle",
    "triangle_outline",
    "diamond",
    "star",
    "dot",
)


def shape(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    kind: str,
    *,
    size: int = 16,
) -> None:
    """Small filled category shape. Kind maps to visual marker."""
    r = size // 2
    if kind == "circle":
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    elif kind == "square":
        draw.rectangle([cx - r, cy - r, cx + r, cy + r], fill=0)
    elif kind == "triangle":
        draw.polygon([(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)], fill=0)
    elif kind == "triangle_outline":
        draw.polygon(
            [(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)],
            outline=0,
            width=2,
        )
    elif kind == "diamond":
        draw.polygon(
            [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=0
        )
    elif kind == "star":
        pts = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r // 2
            pts.append((cx + rr * math.cos(angle), cy + rr * math.sin(angle)))
        draw.polygon(pts, fill=0)
    else:
        draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=0)
