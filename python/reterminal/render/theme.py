"""Typography and spacing tokens for monochrome scene rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MonoTheme:
    outer_margin: int = 28
    inner_margin: int = 16
    gutter: int = 14
    line_width: int = 2
    panel_radius: int = 0
    section_gap: int = 12
    footer_height: int = 24
    card_padding: int = 12
    kicker_height: int = 18
    rule_inset: int = 2


DEFAULT_THEME = MonoTheme()
