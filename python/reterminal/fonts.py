"""Platform-aware font loading utilities."""

import platform
from pathlib import Path
from typing import Optional, List

from PIL import ImageFont
from loguru import logger

# Font search paths by platform
FONT_PATHS = {
    "Darwin": [  # macOS
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        "/Library/Fonts/Courier New.ttf",
    ],
    "Linux": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    ],
    "Windows": [
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "C:/Windows/Fonts/lucon.ttf",
    ],
}

# Cache for loaded fonts
_font_cache: dict = {}


def find_system_font() -> Optional[Path]:
    """Find a suitable monospace font on the current platform."""
    system = platform.system()
    paths = FONT_PATHS.get(system, [])

    for font_path in paths:
        path = Path(font_path)
        if path.exists():
            logger.debug(f"Found system font: {path}")
            return path

    logger.warning(f"No system monospace font found for {system}")
    return None


def load_font(path: Optional[str] = None, size: int = 48) -> ImageFont.FreeTypeFont:
    """
    Load a font with caching.

    Args:
        path: Path to TTF font file (uses system font if None)
        size: Font size in pixels

    Returns:
        PIL ImageFont object
    """
    cache_key = (path, size)

    if cache_key in _font_cache:
        return _font_cache[cache_key]

    font = None

    if path:
        try:
            font = ImageFont.truetype(path, size)
        except OSError as e:
            logger.warning(f"Failed to load font {path}: {e}")

    if font is None:
        system_font = find_system_font()
        if system_font:
            try:
                font = ImageFont.truetype(str(system_font), size)
            except OSError as e:
                logger.warning(f"Failed to load system font: {e}")

    if font is None:
        logger.warning("Using PIL default font")
        font = ImageFont.load_default()

    _font_cache[cache_key] = font
    return font


def load_font_family(
    size_title: int = 36,
    size_large: int = 56,
    size_medium: int = 32,
    size_small: int = 24,
) -> dict:
    """
    Load a family of fonts at different sizes.

    Returns:
        Dict with keys: title, large, medium, small
    """
    return {
        "title": load_font(size=size_title),
        "large": load_font(size=size_large),
        "medium": load_font(size=size_medium),
        "small": load_font(size=size_small),
    }
