"""Renderer + SceneProvider for the summer-camp grid.

Reads a markdown camp table (e.g. the Madad Wiki `family-summer-2026-camps.md`)
via `reterminal.family.camps.parse_camps` and draws a week-by-week grid:
week | boys (together) | Laila. The source's Notes/cost column is dropped by
the parser; emoji are stripped here so Helvetica.ttc does not render tofu.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from PIL import Image

from reterminal.family.camps import DEFAULT_PATH, Camp, parse_camps
from reterminal.payloads import JSONValue
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import (
    BODY,
    BODY_BOLD,
    HEADLINE,
    HEIGHT,
    KICKER,
    MARGIN,
    WIDTH,
    draw_kicker,
    draw_rule,
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
    cleaned = _EMOJI_RE.sub("", text).strip()
    return re.sub(r"^CoderSchool:\s*", "", cleaned, flags=re.IGNORECASE)


def _camp_date(camp: Camp, year: int) -> date | None:
    try:
        return datetime.strptime(f"{camp.week} {year}", "%b %d %Y").date()
    except ValueError:
        return None


def _current_camp_index(camps: list[Camp], today: date) -> int:
    starts = [_camp_date(camp, today.year) for camp in camps]
    dated = [(index, start) for index, start in enumerate(starts) if start is not None]
    if not dated:
        return 0
    for index, start in dated:
        if start <= today < start + timedelta(days=7):
            return index
    future = [index for index, start in dated if start > today]
    return future[0] if future else dated[-1][0]


def render_camps(
    camps: list[Camp],
    *,
    title: str = "SUMMER 2026",
    today: date | None = None,
) -> Image.Image:
    img, draw = new_canvas()

    if not camps:
        draw_kicker(draw, title)
        draw.text((MARGIN, HEIGHT // 2), "No camp weeks.", font=BODY, fill=0)
        return to_1bit(img)

    today = today or date.today()
    current_index = _current_camp_index(camps, today)
    current = camps[current_index]
    draw_kicker(draw, title, right=f"WEEK OF {current.week.upper()}")

    hero_top, hero_bottom = 64, 218
    draw.rectangle([MARGIN, hero_top, WIDTH - MARGIN, hero_bottom], fill=0)
    draw.text((MARGIN + 16, hero_top + 16), "THIS WEEK", font=KICKER, fill=255)
    draw.text((MARGIN + 16, hero_top + 45), current.week.upper(), font=HEADLINE, fill=255)
    draw.line([(MARGIN + 128, hero_top + 16), (MARGIN + 128, hero_bottom - 16)], fill=255, width=1)

    boys_x = MARGIN + 152
    laila_x = MARGIN + 488
    draw.text((boys_x, hero_top + 18), "AMMAR + HASAN", font=KICKER, fill=255)
    boys = _strip_emoji(current.boys) or "Open week"
    draw.text((boys_x, hero_top + 54), truncate_text(draw, boys, HEADLINE, 310), font=HEADLINE, fill=255)
    draw.text((laila_x, hero_top + 18), "LAILA", font=KICKER, fill=255)
    laila = _strip_emoji(current.laila) or "Open week"
    draw.text((laila_x, hero_top + 54), truncate_text(draw, laila, HEADLINE, 250), font=HEADLINE, fill=255)

    rows = camps[current_index + 1 : current_index + 5]
    rows_top = 254
    draw.text((MARGIN, rows_top), "COMING NEXT", font=KICKER, fill=0)
    draw.text((MARGIN + 116, rows_top), "AMMAR + HASAN", font=KICKER, fill=0)
    draw.text((WIDTH - MARGIN - 210, rows_top), "LAILA", font=KICKER, fill=0)
    draw_rule(draw, rows_top + 22)

    for index, camp in enumerate(rows):
        y = rows_top + 36 + index * 45
        draw.text((MARGIN, y), camp.week, font=BODY_BOLD, fill=0)
        boys = _strip_emoji(camp.boys) or "—"
        draw.text(
            (MARGIN + 116, y),
            truncate_text(draw, boys, BODY, 390),
            font=BODY,
            fill=0,
        )
        laila = _strip_emoji(camp.laila) or "—"
        draw.text(
            (WIDTH - MARGIN - 210, y),
            truncate_text(draw, laila, BODY, 210),
            font=BODY,
            fill=0,
        )

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
            image = render_camps(parse_camps(self.path), title=self.title)
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
