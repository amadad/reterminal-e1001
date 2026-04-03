"""Rendering system for host-generated display scenes."""

from reterminal.render.bitmap import generate_bitmap
from reterminal.render.layout import FittedText, Rect, draw_text_block, fit_text_block
from reterminal.render.mono import MonoRenderer
from reterminal.render.theme import DEFAULT_THEME, MonoTheme

__all__ = [
    "MonoRenderer",
    "MonoTheme",
    "DEFAULT_THEME",
    "Rect",
    "FittedText",
    "fit_text_block",
    "draw_text_block",
    "generate_bitmap",
]
