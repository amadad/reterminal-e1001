"""Shared helpers for the preview_* scripts.

The three preview scripts all render 800x480 1-bit PNGs and want regular/bold
Helvetica at arbitrary sizes. Consolidate the three duplicated helpers here.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from reterminal.providers import build_providers, load_manifest
from reterminal.scenes import SceneSpec

WIDTH, HEIGHT = 800, 480
OUT_DIR = Path("/tmp/reterminal-review")
EXAMPLES_DIR = Path(__file__).resolve().parent
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


def default_kitchen_feed() -> Path:
    env_feed = os.getenv("RETERMINAL_FEED")
    if env_feed:
        return Path(env_feed).expanduser()
    local_feed = EXAMPLES_DIR / "kitchen-display.local.json"
    if local_feed.exists():
        return local_feed
    return EXAMPLES_DIR / "kitchen-display.json"


def load_kitchen_scenes(feed: Path | None = None) -> list[SceneSpec]:
    manifest = load_manifest(feed or default_kitchen_feed())
    scenes: list[SceneSpec] = []
    for provider in build_providers(manifest):
        scenes.extend(provider.fetch())
    return scenes
