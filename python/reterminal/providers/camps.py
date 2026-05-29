"""Renderer + SceneProvider for the summer-camp grid.

Reads a markdown camp table (e.g. the Madad Wiki `family-summer-2026-camps.md`)
via `reterminal.family.camps.parse_camps` and draws a week-by-week grid:
week | boys (together) | Laila. The source's Notes/cost column is dropped by
the parser; emoji are stripped here so Helvetica.ttc does not render tofu.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from PIL import Image

from reterminal.family.camps import DEFAULT_PATH, Camp, parse_camps
from reterminal.payloads import JSONValue
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import (
    BODY,
    BODY_BOLD,
    HEIGHT,
    KICKER,
    MARGIN,
    WIDTH,
    draw_kicker,
    draw_rule,
    draw_source_stamp,
    new_canvas,
    render_notice,
    to_1bit,
    truncate_text,
)
from reterminal.scenes import SceneSpec


_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f9ff"
    "\U0001fa70-\U0001faff"
    "☀-➿"
    "️"
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


def render_camps(
    camps: list[Camp],
    *,
    title: str = "SUMMER 2026",
    source_path: Path | None = None,
) -> Image.Image:
    img, draw = new_canvas()
    body_top = draw_kicker(draw, title)

    if not camps:
        draw.text((MARGIN, HEIGHT // 2), "(no camp weeks)", font=BODY, fill=0)
        draw_source_stamp(draw, source_path, stale_after=timedelta(days=180))
        return to_1bit(img)

    week_x = MARGIN
    boys_x = MARGIN + 116
    laila_x = WIDTH - MARGIN - 210
    laila_w = WIDTH - MARGIN - laila_x
    boys_w = laila_x - boys_x - 16

    draw.text((week_x, body_top), "WEEK", font=KICKER, fill=0)
    draw.text((boys_x, body_top), "AMMAR + HASAN", font=KICKER, fill=0)
    draw.text((laila_x, body_top), "LAILA", font=KICKER, fill=0)
    rule_y = body_top + 22
    draw_rule(draw, rule_y)

    rows_top = rule_y + 12
    rows_bottom = HEIGHT - MARGIN - 8
    shown = camps[:10]
    row_h = (rows_bottom - rows_top) // len(shown)

    for i, c in enumerate(shown):
        y = rows_top + i * row_h
        draw.text((week_x, y), truncate_text(draw, c.week, BODY_BOLD, 108), font=BODY_BOLD, fill=0)
        boys = _strip_emoji(c.boys)
        if boys:
            draw.text((boys_x, y), truncate_text(draw, boys, BODY, boys_w), font=BODY, fill=0)
        laila = _strip_emoji(c.laila)
        draw.text(
            (laila_x, y),
            truncate_text(draw, laila or "—", BODY, laila_w),
            font=BODY,
            fill=0,
        )

    draw_source_stamp(draw, source_path, stale_after=timedelta(days=180))
    return to_1bit(img)


class CampsProvider:
    name = "camps"

    def __init__(self, path: Path | str = DEFAULT_PATH, title: str = "SUMMER 2026"):
        self.path = Path(path).expanduser()
        self.title = title

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            image = render_notice("Summer", "camps source missing", str(self.path))
        else:
            image = render_camps(parse_camps(self.path), title=self.title, source_path=self.path)
        return [
            SceneSpec(
                id="camps",
                kind="prerendered",
                title=self.title,
                priority=60,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, JSONValue]) -> CampsProvider:
    path = config.get("path", str(DEFAULT_PATH))
    title = config.get("title", "SUMMER 2026")
    return CampsProvider(path=path, title=title if isinstance(title, str) else "SUMMER 2026")


register_provider("camps", _factory)
