"""Renderer + SceneProvider for the calendar kitchen page.

Reads `calendar.md` via `reterminal.family.calendar.parse_calendar` and
draws a two-column today/tomorrow board. Slot pinning is owned by the
provider manifest. The provider has no calendar API dependency and never
makes a network call; if the file is missing, a visible notice is shown.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from reterminal.family.calendar import DEFAULT_PATH, CalendarItem, parse_calendar
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import (
    HEIGHT,
    WIDTH,
    draw_source_stamp,
    font,
    render_notice,
    to_1bit,
)
from reterminal.scenes import SceneSpec


# Helvetica.ttc has no emoji glyphs, so labels like "🏟️ Baseball" render as
# tofu boxes on the panel. Strip emoji and variation selectors at render
# time so the source can keep semantic emoji for upstream tooling.
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f9ff"  # symbols & pictographs, transport, supplemental
    "\U0001fa70-\U0001faff"  # symbols and pictographs extended-A
    "☀-➿"            # misc symbols, dingbats
    "️"                   # variation selector-16
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    label = text
    while draw.textlength(label, font=font) > max_w and len(label) > 4:
        label = label[:-2] + "…"
    return label


def _render_column(
    draw: ImageDraw.ImageDraw,
    items: list[CalendarItem],
    *,
    x: int,
    y: int,
    width: int,
    bottom: int,
    title: str,
) -> None:
    title_f = font(18, "bold")
    time_f = font(20, "bold")
    label_f = font(24)
    who_f = font(14)

    draw.text((x, y), title, font=title_f, fill=0)
    draw.line([(x, y + 28), (x + width, y + 28)], fill=0, width=1)

    cursor = y + 44
    if not items:
        draw.text((x, cursor), "(nothing scheduled)", font=label_f, fill=0)
        return

    for item in items:
        if cursor > bottom - 30:
            break
        time_str = item.time or "—"
        time_w = draw.textlength(time_str, font=time_f)
        draw.text((x, cursor), time_str, font=time_f, fill=0)
        label_x = x + max(int(time_w), 80) + 12
        label = _truncate(draw, _strip_emoji(item.label), label_f, x + width - label_x)
        draw.text((label_x, cursor + 2), label, font=label_f, fill=0)
        if item.who:
            who_str = f"@{item.who}"
            who_w = draw.textlength(who_str, font=who_f)
            draw.text((x + width - who_w, cursor + 32), who_str, font=who_f, fill=0)
        cursor += 48


def render_calendar(
    today: list[CalendarItem],
    tomorrow: list[CalendarItem],
    *,
    source_path: Path | None = None,
) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"
    margin = 24
    gutter = 28

    draw.text((margin, margin), "AGENDA", font=font(13, "bold"), fill=0)

    body_top = margin + 30
    body_bottom = HEIGHT - margin
    col_w = (WIDTH - margin * 2 - gutter) // 2

    _render_column(
        draw, today,
        x=margin, y=body_top, width=col_w, bottom=body_bottom,
        title="TODAY",
    )
    _render_column(
        draw, tomorrow,
        x=margin + col_w + gutter, y=body_top, width=col_w, bottom=body_bottom,
        title="TOMORROW",
    )

    draw_source_stamp(draw, source_path, stale_after=timedelta(hours=2))
    return to_1bit(img)


class CalendarProvider:
    name = "calendar"

    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path).expanduser()

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            image = render_notice("Agenda", "calendar source missing", str(self.path))
        else:
            today, tomorrow = parse_calendar(self.path)
            image = render_calendar(today, tomorrow, source_path=self.path)
        return [
            SceneSpec(
                id="calendar",
                kind="prerendered",
                title="Agenda",
                priority=100,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, Any]) -> CalendarProvider:
    path = config.get("path", str(DEFAULT_PATH))
    return CalendarProvider(path=path)


register_provider("calendar", _factory)
