"""Platform-aware font loading utilities."""

from __future__ import annotations

import platform
from pathlib import Path

from PIL import ImageFont
from loguru import logger

FONT_PATHS = {
    "sans": {
        "Darwin": [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
        ],
        "Linux": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ],
        "Windows": [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ],
    },
    "mono": {
        "Darwin": [
            "/System/Library/Fonts/Menlo.ttc",
            "/System/Library/Fonts/Monaco.ttf",
            "/Library/Fonts/Courier New.ttf",
        ],
        "Linux": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        ],
        "Windows": [
            "C:/Windows/Fonts/consola.ttf",
            "C:/Windows/Fonts/cour.ttf",
            "C:/Windows/Fonts/lucon.ttf",
        ],
    },
}

_font_cache: dict[tuple[str | None, int, str], ImageFont.FreeTypeFont] = {}


def find_system_font(kind: str = "sans") -> Path | None:
    """Find a suitable system font for the current platform."""
    system = platform.system()
    paths = FONT_PATHS.get(kind, {}).get(system, [])

    for font_path in paths:
        path = Path(font_path)
        if path.exists():
            logger.debug(f"Found {kind} font: {path}")
            return path

    logger.warning(f"No {kind} font found for {system}")
    if kind != "mono":
        return find_system_font("mono")
    return None


def load_font(
    path: str | None = None,
    size: int = 48,
    *,
    kind: str = "sans",
) -> ImageFont.FreeTypeFont:
    """Load a font with caching."""
    cache_key = (path, size, kind)
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    font = None
    if path:
        try:
            font = ImageFont.truetype(path, size)
        except OSError as e:
            logger.warning(f"Failed to load font {path}: {e}")

    if font is None:
        system_font = find_system_font(kind)
        if system_font:
            try:
                font = ImageFont.truetype(str(system_font), size)
            except OSError as e:
                logger.warning(f"Failed to load {kind} system font: {e}")

    if font is None:
        logger.warning("Using PIL default font")
        font = ImageFont.load_default()

    _font_cache[cache_key] = font
    return font


def load_mono_font(path: str | None = None, size: int = 18) -> ImageFont.FreeTypeFont:
    """Load a monospace font for folios, labels, and compact metadata."""
    return load_font(path=path, size=size, kind="mono")

