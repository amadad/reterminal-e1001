"""Measurement-aware layout primitives for monochrome scenes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PIL import ImageDraw

from reterminal.fonts import load_font


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def inset(self, amount: int) -> "Rect":
        return Rect(
            self.x + amount,
            self.y + amount,
            max(1, self.width - amount * 2),
            max(1, self.height - amount * 2),
        )

    def split_top(self, height: int, *, gap: int = 0) -> tuple["Rect", "Rect"]:
        top_height = max(1, min(height, self.height))
        remainder_height = max(1, self.height - top_height - gap)
        return (
            Rect(self.x, self.y, self.width, top_height),
            Rect(self.x, self.y + top_height + gap, self.width, remainder_height),
        )

    def split_bottom(self, height: int, *, gap: int = 0) -> tuple["Rect", "Rect"]:
        bottom_height = max(1, min(height, self.height))
        remainder_height = max(1, self.height - bottom_height - gap)
        return (
            Rect(self.x, self.y, self.width, remainder_height),
            Rect(self.x, self.bottom - bottom_height, self.width, bottom_height),
        )

    def split_left(self, width: int, *, gap: int = 0) -> tuple["Rect", "Rect"]:
        left_width = max(1, min(width, self.width))
        remainder_width = max(1, self.width - left_width - gap)
        return (
            Rect(self.x, self.y, left_width, self.height),
            Rect(self.x + left_width + gap, self.y, remainder_width, self.height),
        )

    def split_right(self, width: int, *, gap: int = 0) -> tuple["Rect", "Rect"]:
        right_width = max(1, min(width, self.width))
        remainder_width = max(1, self.width - right_width - gap)
        return (
            Rect(self.x, self.y, remainder_width, self.height),
            Rect(self.right - right_width, self.y, right_width, self.height),
        )

    def columns(self, count: int, *, gap: int = 0) -> list["Rect"]:
        if count <= 0:
            return []
        total_gap = gap * (count - 1)
        usable_width = max(1, self.width - total_gap)
        base = usable_width // count
        remainder = usable_width % count

        columns: list[Rect] = []
        x = self.x
        for index in range(count):
            width = base + (1 if index < remainder else 0)
            columns.append(Rect(x, self.y, width, self.height))
            x += width + gap
        return columns

    def rows(self, count: int, *, gap: int = 0) -> list["Rect"]:
        if count <= 0:
            return []
        total_gap = gap * (count - 1)
        usable_height = max(1, self.height - total_gap)
        base = usable_height // count
        remainder = usable_height % count

        rows: list[Rect] = []
        y = self.y
        for index in range(count):
            height = base + (1 if index < remainder else 0)
            rows.append(Rect(self.x, y, self.width, height))
            y += height + gap
        return rows


@dataclass(slots=True)
class FittedText:
    lines: list[str]
    font_size: int
    font: object
    line_height: int
    height: int
    overflowed: bool = False


def fit_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    rect: Rect,
    *,
    max_font_size: int,
    min_font_size: int,
    max_lines: int,
    line_spacing: int = 4,
) -> FittedText:
    """Fit text into a bounded rectangle using wrap + shrink + ellipsis."""
    normalized = " ".join(text.split())
    if not normalized:
        font = load_font(size=max_font_size)
        line_height = _line_height(draw, font)
        return FittedText(lines=[""], font_size=max_font_size, font=font, line_height=line_height, height=line_height)

    best: FittedText | None = None
    for size in range(max_font_size, min_font_size - 1, -2):
        font = load_font(size=size)
        line_height = _line_height(draw, font)
        allowed_lines = min(max_lines, _max_lines_for_height(line_height, line_spacing, rect.height))
        lines = wrap_text(draw, normalized, font, rect.width)
        overflowed = len(lines) > allowed_lines
        if overflowed:
            lines = clamp_lines(draw, lines, font, rect.width, allowed_lines)
        height = len(lines) * line_height + max(0, len(lines) - 1) * line_spacing
        candidate = FittedText(
            lines=lines,
            font_size=size,
            font=font,
            line_height=line_height,
            height=height,
            overflowed=overflowed,
        )
        best = candidate
        if height <= rect.height:
            return candidate

    assert best is not None
    return best


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    rect: Rect,
    fitted: FittedText,
    *,
    align: Literal["left", "center", "right"] = "left",
    valign: Literal["top", "center", "bottom"] = "top",
    fill: int = 0,
    line_spacing: int = 4,
) -> None:
    """Draw a pre-fitted text block inside a rectangle."""
    y = rect.y
    if valign == "center":
        y = rect.y + max(0, (rect.height - fitted.height) // 2)
    elif valign == "bottom":
        y = rect.bottom - fitted.height

    for line in fitted.lines:
        bbox = draw.textbbox((0, 0), line, font=fitted.font)
        line_width = bbox[2] - bbox[0]
        if align == "center":
            x = rect.x + max(0, (rect.width - line_width) // 2)
        elif align == "right":
            x = rect.right - line_width
        else:
            x = rect.x
        draw.text((x, y), line, font=fitted.font, fill=fill)
        y += fitted.line_height + line_spacing


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_width(draw, candidate, font) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def clamp_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font,
    width: int,
    max_lines: int,
) -> list[str]:
    if len(lines) <= max_lines:
        return lines

    clamped = lines[:max_lines]
    clamped[-1] = ellipsize(draw, clamped[-1], font, width)
    return clamped


def ellipsize(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    candidate = text.strip()
    if not candidate:
        return "…"
    if text_width(draw, candidate, font) <= width:
        return candidate if candidate.endswith("…") else candidate + "…"

    while candidate and text_width(draw, candidate + "…", font) > width:
        candidate = candidate[:-1].rstrip()
    return (candidate + "…") if candidate else "…"


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _line_height(draw: ImageDraw.ImageDraw, font) -> int:
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    return bbox[3] - bbox[1]


def _max_lines_for_height(line_height: int, line_spacing: int, height: int) -> int:
    lines = 1
    while (lines + 1) * line_height + lines * line_spacing <= height:
        lines += 1
    return max(1, lines)
