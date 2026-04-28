"""Shared helpers for the preview_* scripts.

The three preview scripts all render 800x480 1-bit PNGs and want regular/bold
Helvetica at arbitrary sizes. Consolidate the three duplicated helpers here.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 480
OUT_DIR = Path("/tmp/reterminal-review")
HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")
_FACE_INDEX = {"regular": 0, "bold": 1}


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    """Helvetica at `size`, regular or bold. PIL default font as fallback."""
    if not HELVETICA.exists():
        return ImageFont.load_default()
    return ImageFont.truetype(str(HELVETICA), size, index=_FACE_INDEX.get(weight, 0))


def new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Grayscale 800x480 canvas on white; draw in `fill=0` for black pixels."""
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    return img, ImageDraw.Draw(img)


def to_1bit(img: Image.Image) -> Image.Image:
    """Hard black/white threshold at 192. Keeps text-heavy scenes crisp."""
    return img.point(lambda x: 255 if x >= 192 else 0, mode="1")
