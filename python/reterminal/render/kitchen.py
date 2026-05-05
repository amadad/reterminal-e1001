"""Shared drawing helpers for markdown-backed kitchen-display renderers."""

from __future__ import annotations

from datetime import datetime, timedelta
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


def draw_source_stamp(
    draw: ImageDraw.ImageDraw,
    source_path: Path | None,
    *,
    stale_after: timedelta | None = None,
    now: datetime | None = None,
) -> None:
    """Draw the bottom-right "UPDATED ..." stamp for a source file.

    When `stale_after` is provided and the file's mtime is older than that
    threshold, the stamp is replaced with a black `STALE` pill so a dead
    upstream writer (e.g. the calendar heartbeat) becomes visible in the
    kitchen instead of silently freezing the display.
    """
    if source_path is None or not source_path.exists():
        return
    mtime = datetime.fromtimestamp(source_path.stat().st_mtime)
    stale = (
        stale_after is not None
        and (now or datetime.now()) - mtime > stale_after
    )
    stamp_font = font(10)
    if stale:
        label = f"STALE  {mtime.strftime('%b %-d %H:%M')}"
        text_w = draw.textlength(label, font=stamp_font)
        pad_x, pad_y = 6, 3
        x1 = WIDTH - 24 - text_w - pad_x * 2
        y1 = HEIGHT - 22 - pad_y
        x2 = WIDTH - 24
        y2 = HEIGHT - 22 + 12 + pad_y
        draw.rectangle([x1, y1, x2, y2], fill=0)
        draw.text((x1 + pad_x, y1 + pad_y - 1), label, font=stamp_font, fill=255)
    else:
        stamp = mtime.strftime("UPDATED %b %-d %H:%M")
        text_w = draw.textlength(stamp, font=stamp_font)
        draw.text((WIDTH - 24 - text_w, HEIGHT - 18), stamp, font=stamp_font, fill=0)


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
