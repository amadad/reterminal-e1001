"""Shared drawing helpers for markdown-backed kitchen-display renderers."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from reterminal.config import HEIGHT, WIDTH

HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")
_FACE_INDEX = {"regular": 0, "bold": 1}


@lru_cache(maxsize=128)
def font(size: int, weight: str = "regular") -> ImageFont.ImageFont:
    if not HELVETICA.exists():
        return ImageFont.load_default()
    return ImageFont.truetype(str(HELVETICA), size, index=_FACE_INDEX.get(weight, 0))


def to_1bit(img: Image.Image) -> Image.Image:
    return img.point(lambda x: 255 if x >= 192 else 0, mode="1")


def new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"  # binary rasterization — prevents antialiased grey pixels after 1-bit threshold
    return img, draw


def truncate_text(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.ImageFont, max_w: int) -> str:
    label = text
    while draw.textlength(label, font=f) > max_w and len(label) > 4:
        label = label[:-2] + "…"
    return label


def draw_source_stamp(
    draw: ImageDraw.ImageDraw,
    source_path: Path | None,
    *,
    stale_after: timedelta | None = None,
    now: datetime | None = None,
) -> None:
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


# ── design system ──────────────────────────────────────────────────────────
# The code half of the kitchen-display design system; docs/design.md is the
# intent half. Renderers compose from these tokens instead of hardcoding sizes,
# margins, and header drawing, so the slots share one visual language (unity)
# while their bodies stay free to differ (not uniformity). The snapshot goldens
# in tests/test_renderer_snapshots.py pin the result — change a token here,
# update docs/design.md in the same edit, and re-pin the goldens.

# Spacing: one base unit; every margin/gap is a multiple, for shared rhythm.
BASE = 8
MARGIN = 3 * BASE  # 24 — outer frame
GUTTER = 3 * BASE  # 24 — column gap

# Type ladder (Helvetica): a finite, named set of roles. Renderers reference
# the role, not a raw size. Dense compositions (the missions 4-up grid) may
# step a role down one rung inside a cell — the one documented exception.
KICKER = font(13, "bold")    # slot label (top-left, UPPERCASE); also column heads
META = font(16)              # dates, counts, secondary text
SUBHEAD = font(18, "bold")   # in-body section header (TODAY, RECENT, UP NEXT)
BODY = font(22)              # primary list text
BODY_BOLD = font(22, "bold")
HEADLINE = font(28, "bold")  # hero / item headline
DISPLAY = font(54, "bold")   # big numerals (countdowns)

# Iconography: the one canonical tag→shape map (viz.py owns the primitives),
# centralized so events and comingup share it instead of each defining a copy.
TAG_SHAPES = {
    "trip": "triangle",
    "school": "square",
    "event": "circle",
    "performance": "diamond",
    "camp": "triangle_outline",
    "celebration": "star",
}
DEFAULT_SHAPE = "dot"


def shape_for(tag: str | None) -> str:
    return TAG_SHAPES.get((tag or "").lower(), DEFAULT_SHAPE)


def draw_kicker(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    right: str | None = None,
) -> int:
    """Standard slot header: UPPERCASE kicker at the top-left, optional
    right-aligned meta on the same baseline. Returns the y where body content
    should begin, so every slot opens the same way.
    """
    draw.text((MARGIN, MARGIN), text.upper(), font=KICKER, fill=0)
    if right:
        w = draw.textlength(right, font=KICKER)
        draw.text((WIDTH - MARGIN - w, MARGIN), right, font=KICKER, fill=0)
    return MARGIN + 4 * BASE  # body top = 56


def draw_rule(draw: ImageDraw.ImageDraw, y: int, *, x0: int = MARGIN, x1: int | None = None) -> None:
    """A standard 1px rule inset to the margins."""
    draw.line([(x0, y), (WIDTH - MARGIN if x1 is None else x1, y)], fill=0, width=1)


def render_notice(title: str, message: str, detail: str | None = None) -> Image.Image:
    img, draw = new_canvas()
    draw_kicker(draw, title)
    draw.text((MARGIN, 190), message, font=font(34, "bold"), fill=0)
    if detail:
        draw.text((MARGIN, 238), truncate_text(draw, detail, META, WIDTH - 2 * MARGIN), font=META, fill=0)
    return to_1bit(img)
