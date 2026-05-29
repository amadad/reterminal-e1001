"""Renderer + SceneProvider for the calendar kitchen page.

Reads `calendar.md` via `reterminal.family.calendar.parse_calendar`. The
file's `## YYYY-MM-DD` headers are the source of truth for which events
belong to which day; the renderer asks `date.today()` at render time and
draws the matching sections under "TODAY · Fri May 8" / "TOMORROW · Sat
May 9". This makes a stale upstream writer produce an empty-and-dated
column rather than yesterday's events labeled as today's.

Slot pinning is owned by the provider manifest. The provider has no
calendar API dependency and never makes a network call.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path
from PIL import Image, ImageDraw

from reterminal.family.calendar import (
    DEFAULT_PATH,
    CalendarItem,
    events_for,
    parse_calendar,
)
from reterminal.payloads import JSONValue
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import (
    BODY,
    HEIGHT,
    MARGIN,
    SUBHEAD,
    WIDTH,
    draw_kicker,
    draw_source_stamp,
    font,
    new_canvas,
    render_notice,
    to_1bit,
    truncate_text,
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
    title_f = SUBHEAD
    kid_f = font(16, "bold")  # dense column sub-label; one rung below SUBHEAD
    time_f = SUBHEAD
    label_f = BODY

    title_text = truncate_text(draw, title, title_f, width)
    draw.text((x, y), title_text, font=title_f, fill=0)
    draw.line([(x, y + 28), (x + width, y + 28)], fill=0, width=1)

    cursor = y + 44
    if not items:
        draw.text((x, cursor), "(nothing scheduled)", font=label_f, fill=0)
        return

    groups: dict[str, list[CalendarItem]] = {}
    for item in items:
        key = item.who or "(unassigned)"
        groups.setdefault(key, []).append(item)

    indent = 12
    for kid, kid_items in groups.items():
        if cursor > bottom - 26:
            break
        draw.text((x, cursor), kid.upper(), font=kid_f, fill=0)
        cursor += 22
        for item in kid_items:
            if cursor > bottom - 22:
                break
            time_str = item.time or "—"
            time_w = draw.textlength(time_str, font=time_f)
            draw.text((x + indent, cursor), time_str, font=time_f, fill=0)
            label_x = x + indent + max(int(time_w), 64) + 8
            label = truncate_text(draw, _strip_emoji(item.label), label_f, x + width - label_x)
            draw.text((label_x, cursor + 1), label, font=label_f, fill=0)
            cursor += 26
        cursor += 8


def render_calendar(
    todays: list[CalendarItem],
    tomorrows: list[CalendarItem],
    *,
    today: date,
    source_path: Path | None = None,
    dropped: int = 0,
) -> Image.Image:
    img, draw = new_canvas()
    margin = MARGIN
    gutter = 28

    body_top = draw_kicker(draw, "Agenda")
    body_bottom = HEIGHT - margin
    col_w = (WIDTH - margin * 2 - gutter) // 2

    tomorrow = today + timedelta(days=1)
    today_title = f"TODAY · {today.strftime('%a %b %-d')}"
    tomorrow_title = f"TOMORROW · {tomorrow.strftime('%a %b %-d')}"

    _render_column(
        draw, todays,
        x=margin, y=body_top, width=col_w, bottom=body_bottom,
        title=today_title,
    )
    _render_column(
        draw, tomorrows,
        x=margin + col_w + gutter, y=body_top, width=col_w, bottom=body_bottom,
        title=tomorrow_title,
    )

    if dropped:
        warn_f = font(12)
        warn = f"({dropped} line{'s' if dropped != 1 else ''} couldn't parse — see lint)"
        draw.text((margin, HEIGHT - margin - 12), warn, font=warn_f, fill=0)

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
            parsed = parse_calendar(self.path)
            if parsed.legacy_headers and not parsed.by_date:
                image = render_notice(
                    "Agenda",
                    "retired calendar.md schema",
                    "writer must emit `## YYYY-MM-DD Day` headers",
                )
            else:
                today = date.today()
                tomorrow = today + timedelta(days=1)
                image = render_calendar(
                    events_for(parsed, today),
                    events_for(parsed, tomorrow),
                    today=today,
                    source_path=self.path,
                    dropped=parsed.dropped,
                )
        return [
            SceneSpec(
                id="calendar",
                kind="prerendered",
                title="Agenda",
                priority=100,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, JSONValue]) -> CalendarProvider:
    path = config.get("path", str(DEFAULT_PATH))
    return CalendarProvider(path=path)


register_provider("calendar", _factory)
