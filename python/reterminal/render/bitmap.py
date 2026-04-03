"""Deterministic bitmap generators for monochrome poster scenes."""

from __future__ import annotations

from typing import Iterable

from PIL import Image, ImageDraw, ImageOps


def generate_bitmap(spec: dict, width: int, height: int) -> Image.Image:
    """Generate a grayscale bitmap from a small declarative spec."""
    kind = str(spec.get("kind", "sparkline")).lower()
    image = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(image)

    if kind == "bars":
        _draw_bars(draw, spec, width, height)
    elif kind == "grid":
        _draw_grid(draw, spec, width, height)
    else:
        _draw_sparkline(draw, spec, width, height)

    return ImageOps.autocontrast(image)


def _draw_sparkline(draw: ImageDraw.ImageDraw, spec: dict, width: int, height: int) -> None:
    values = _coerce_values(spec.get("values"))
    if len(values) < 2:
        values = [0.0, 1.0]

    margin_x = 18
    top = 18
    bottom = height - 18
    left = margin_x
    right = width - margin_x

    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum or 1.0
    step = (right - left) / max(1, len(values) - 1)

    points: list[tuple[float, float]] = []
    for index, value in enumerate(values):
        normalized = (value - minimum) / span
        x = left + index * step
        y = bottom - normalized * (bottom - top)
        points.append((x, y))

    baseline = bottom + 2
    draw.line((left, baseline, right, baseline), fill=0, width=2)
    if len(points) > 1:
        draw.line(points, fill=0, width=4)
    for x, y in points[1:-1:2]:
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=255, outline=0)

    last_x, last_y = points[-1]
    draw.ellipse((last_x - 6, last_y - 6, last_x + 6, last_y + 6), fill=0)


def _draw_bars(draw: ImageDraw.ImageDraw, spec: dict, width: int, height: int) -> None:
    values = _coerce_values(spec.get("values"))
    if not values:
        values = [1.0, 2.0, 3.0, 2.0]

    margin = 18
    gap = int(spec.get("gap", 8))
    baseline = height - 18
    top = 20
    available_width = width - margin * 2 - gap * (len(values) - 1)
    bar_width = max(10, available_width // len(values))
    maximum = max(values) or 1.0

    x = margin
    for index, value in enumerate(values):
        bar_height = max(8, int((value / maximum) * (baseline - top)))
        y = baseline - bar_height
        fill = 0 if index % 2 == 0 else 64
        draw.rectangle((x, y, x + bar_width, baseline), fill=fill, outline=0, width=2)
        x += bar_width + gap

    draw.line((margin, baseline, width - margin, baseline), fill=0, width=2)


def _draw_grid(draw: ImageDraw.ImageDraw, spec: dict, width: int, height: int) -> None:
    values = spec.get("values") or []
    cells = [bool(value) for value in values]
    if not cells:
        cells = [True, False, True, True, False, True, False, True, True]

    cols = int(spec.get("cols", max(1, round(len(cells) ** 0.5))))
    rows = int(spec.get("rows", (len(cells) + cols - 1) // cols))
    margin = 18
    gap = int(spec.get("gap", 8))

    cell_width = max(10, (width - margin * 2 - gap * (cols - 1)) // cols)
    cell_height = max(10, (height - margin * 2 - gap * (rows - 1)) // rows)

    for index, active in enumerate(cells[: rows * cols]):
        row = index // cols
        col = index % cols
        x = margin + col * (cell_width + gap)
        y = margin + row * (cell_height + gap)
        if active:
            draw.rectangle((x, y, x + cell_width, y + cell_height), fill=0)
        else:
            draw.rectangle((x, y, x + cell_width, y + cell_height), outline=0, width=2)


def _coerce_values(raw: object) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, dict)):
        values: list[float] = []
        for item in raw:
            try:
                values.append(float(item))
            except (TypeError, ValueError):
                continue
        return values
    return []
