"""Typography and spacing tokens for monochrome scene rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MonoTheme:
    outer_margin: int = 12
    inner_margin: int = 8
    gutter: int = 8
    line_width: int = 1
    panel_radius: int = 0
    section_gap: int = 4
    footer_height: int = 14
    card_padding: int = 6
    kicker_height: int = 18
    rule_inset: int = 1


DEFAULT_THEME = MonoTheme()
