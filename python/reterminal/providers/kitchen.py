"""Shared drawing helpers for markdown-backed kitchen-display providers."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480
HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")
_FACE_INDEX = {"regular": 0, "bold": 1}


@lru_cache(maxsize=128)
def font(size: int, weight: str = "regular") -> ImageFont.ImageFont:
    if not HELVETICA.exists():
        return ImageFont.load_default()
    return ImageFont.truetype(str(HELVETICA), size, index=_FACE_INDEX.get(weight, 0))


def to_1bit(img: Image.Image) -> Image.Image:
    return img.point(lambda x: 255 if x >= 192 else 0, mode="1")


def draw_source_stamp(draw: ImageDraw.ImageDraw, source_path: Path | None) -> None:
    if source_path is None or not source_path.exists():
        return
    stamp = datetime.fromtimestamp(source_path.stat().st_mtime).strftime("UPDATED %b %-d %H:%M")
    stamp_font = font(10)
    width = draw.textlength(stamp, font=stamp_font)
    draw.text((WIDTH - 24 - width, HEIGHT - 18), stamp, font=stamp_font, fill=0)


def render_notice(title: str, message: str, detail: str | None = None) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)
    draw.text((24, 24), title.upper(), font=font(14, "bold"), fill=0)
    draw.text((24, 190), message, font=font(34, "bold"), fill=0)
    if detail:
        text = detail
        while draw.textlength(text, font=font(16)) > WIDTH - 48 and len(text) > 4:
            text = text[:-2] + "…"
        draw.text((24, 238), text, font=font(16), fill=0)
    return to_1bit(img)
