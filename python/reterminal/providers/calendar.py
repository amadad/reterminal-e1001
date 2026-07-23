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
    BODY_BOLD,
    DISPLAY,
    HEADLINE,
    HEIGHT,
    KICKER,
    MARGIN,
    META,
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
    cleaned = _EMOJI_RE.sub("", text).strip()
    return re.sub(r"^Camp week \d+\s*-\s*(?:CoderSchool:\s*)?", "", cleaned, flags=re.IGNORECASE)


def _draw_today_items(
    draw: ImageDraw.ImageDraw,
    items: list[CalendarItem],
    *,
    x: int,
    y: int,
    width: int,
) -> None:
    if not items:
        draw.text((x, y), "Nothing scheduled.", font=BODY, fill=0)
        return

    time_w = 108
    for index, item in enumerate(items[:5]):
        row_y = y + index * 54
        time_label = item.time or "ALL DAY"
        draw.text((x, row_y), time_label, font=BODY_BOLD, fill=0)
        content_x = x + time_w
        if item.who:
            draw.text((content_x, row_y + 1), item.who.upper(), font=KICKER, fill=0)
            label_y = row_y + 19
        else:
            label_y = row_y
        label = truncate_text(draw, _strip_emoji(item.label), BODY, width - time_w)
        draw.text((content_x, label_y), label, font=BODY, fill=0)


def _draw_tomorrow_panel(
    draw: ImageDraw.ImageDraw,
    items: list[CalendarItem],
    *,
    tomorrow: date,
    x: int,
    width: int,
) -> None:
    top, bottom = 64, 446
    draw.rectangle([x, top, x + width, bottom], fill=0)
    draw.text((x + 16, top + 16), "TOMORROW", font=KICKER, fill=255)
    day_label = str(tomorrow.day)
    draw.text((x + 16, top + 42), day_label, font=DISPLAY, fill=255)
    weekday_x = x + 30 + draw.textlength(day_label, font=DISPLAY)
    draw.text((weekday_x, top + 72), tomorrow.strftime("%A").upper(), font=KICKER, fill=255)
    draw.line([(x + 16, top + 116), (x + width - 16, top + 116)], fill=255, width=1)

    if not items:
        draw.text((x + 16, top + 140), "Nothing scheduled.", font=BODY, fill=255)
        return

    cursor = top + 140
    inner_w = width - 32
    for item in items[:4]:
        time_label = item.time or "ALL DAY"
        draw.text((x + 16, cursor), time_label, font=META, fill=255)
        if item.who:
            who_w = draw.textlength(item.who.upper(), font=KICKER)
            draw.text((x + width - 16 - who_w, cursor + 2), item.who.upper(), font=KICKER, fill=255)
        label = truncate_text(draw, _strip_emoji(item.label), BODY, inner_w)
        draw.text((x + 16, cursor + 23), label, font=BODY, fill=255)
        cursor += 66


def render_calendar(
    todays: list[CalendarItem],
    tomorrows: list[CalendarItem],
    *,
    today: date,
    source_path: Path | None = None,
    dropped: int = 0,
) -> Image.Image:
    img, draw = new_canvas()
    draw_kicker(draw, "Agenda", right=today.strftime("%A · %b %-d").upper())

    panel_w = 216
    panel_x = WIDTH - MARGIN - panel_w
    today_w = panel_x - MARGIN - 24

    date_top = 64
    draw.rectangle([MARGIN, date_top, MARGIN + 112, date_top + 96], fill=0)
    draw.text((MARGIN + 12, date_top + 4), str(today.day), font=DISPLAY, fill=255)
    draw.text((MARGIN + 14, date_top + 70), today.strftime("%b").upper(), font=KICKER, fill=255)
    draw.text((MARGIN + 136, date_top + 12), "TODAY", font=HEADLINE, fill=0)
    count_label = f"{len(todays)} ITEM{'S' if len(todays) != 1 else ''}"
    draw.text((MARGIN + 136, date_top + 54), count_label, font=META, fill=0)
    draw.line([(MARGIN, 176), (MARGIN + today_w, 176)], fill=0, width=1)

    _draw_today_items(draw, todays, x=MARGIN, y=190, width=today_w)
    _draw_tomorrow_panel(draw, tomorrows, tomorrow=today + timedelta(days=1), x=panel_x, width=panel_w)

    if dropped:
        warn_f = font(12)
        warn = f"({dropped} line{'s' if dropped != 1 else ''} couldn't parse — see lint)"
        draw.text((MARGIN, HEIGHT - MARGIN - 12), warn, font=warn_f, fill=0)

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
