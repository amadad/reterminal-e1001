"""Typography and spacing tokens for monochrome scene rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MonoTheme:
    outer_margin: int = 40
    inner_margin: int = 24
    gutter: int = 18
    line_width: int = 3
    panel_radius: int = 0


DEFAULT_THEME = MonoTheme()
