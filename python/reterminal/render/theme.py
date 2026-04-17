"""Typography and spacing tokens for monochrome scene rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MonoTheme:
    outer_margin: int = 16
    inner_margin: int = 10
    gutter: int = 10
    line_width: int = 1
    panel_radius: int = 0
    section_gap: int = 8
    footer_height: int = 18
    card_padding: int = 8
    kicker_height: int = 22
    rule_inset: int = 2


DEFAULT_THEME = MonoTheme()
