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
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image

from reterminal.family.calendar import (
    DEFAULT_PATH,
    CalendarItem,
    events_for,
    parse_calendar,
)
from reterminal.family.agenda import CalendarDay, calendar_days, upcoming_events, weekend_start, remaining_today
from reterminal.render.agenda import render_day_columns, render_next, render_week, render_weekend, render_prepare
from reterminal.payloads import JSONValue
from reterminal.providers.manifest import register_provider
from reterminal.render.kitchen import render_notice
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



def render_calendar(
    todays: list[CalendarItem],
    tomorrows: list[CalendarItem],
    *,
    today: date,
    source_path: Path | None = None,
    dropped: int = 0,
    tomorrow_available: bool = True,
    checked_at: datetime | None = None,
) -> Image.Image:
    days = [
        CalendarDay(today, tuple(todays), True, remaining=True),
        CalendarDay(today + timedelta(days=1), tuple(tomorrows), tomorrow_available),
    ]
    return render_day_columns(
        days, title="Now", headings=("Today", "Tomorrow"), source_path=source_path,
        notice="Some calendar entries could not be read" if dropped else None,
        checked_at=checked_at,
    )


class CalendarProvider:
    name = "calendar"

    def __init__(self, path: Path | str = DEFAULT_PATH, *, view: str = "now"):
        if view not in {"now", "week", "next", "weekend", "prepare"}:
            raise ValueError("calendar view must be now, week, next, weekend, or prepare")
        self.path = Path(path).expanduser()
        self.view = view

    def fetch(self) -> list[SceneSpec]:
        if not self.path.exists():
            image = render_notice("Agenda", "calendar source missing", str(self.path))
        else:
            try:
                parsed = parse_calendar(self.path)
            except (ValueError, KeyError, TypeError) as exc:
                image = render_notice("Calendar", "calendar source invalid", str(exc))
                return [SceneSpec(id=f"calendar-{self.view}", kind="prerendered", title=self.view.title(), priority=100, prerendered=image)]
            now = datetime.now(ZoneInfo(parsed.timezone)) if parsed.timezone else datetime.now()
            if parsed.legacy_headers and not parsed.by_date:
                image = render_notice(
                    "Agenda",
                    "retired calendar.md schema",
                    "writer must emit `## YYYY-MM-DD Day` headers",
                )
            elif now.date() not in parsed.by_date:
                image = render_notice("Calendar", "calendar needs an update", "Today's calendar data is unavailable.")
            elif self.view == "week":
                days = calendar_days(parsed, now.date() + timedelta(days=1), 7)
                image = render_week(days, source_path=self.path, checked_at=parsed.checked_at)
            elif self.view == "next":
                image = render_next(upcoming_events(parsed, now), now=now, source_path=self.path, checked_at=parsed.checked_at)
            elif self.view == "prepare":
                day = calendar_days(parsed, now.date() + timedelta(days=1), 1)[0]
                image = render_prepare(day, source_path=self.path, checked_at=parsed.checked_at)
            elif self.view == "weekend":
                days = calendar_days(parsed, weekend_start(now.date()), 2)
                image = render_weekend(days, source_path=self.path, checked_at=parsed.checked_at)
            else:
                today = now.date()
                tomorrow = today + timedelta(days=1)
                image = render_calendar(
                    remaining_today(events_for(parsed, today), now),
                    events_for(parsed, tomorrow),
                    today=today,
                    source_path=self.path,
                    dropped=parsed.dropped,
                    checked_at=parsed.checked_at,
                    tomorrow_available=tomorrow in parsed.by_date,
                )
        return [
            SceneSpec(
                id="calendar" if self.view == "now" else f"calendar-{self.view}",
                kind="prerendered",
                title=self.view.title(),
                priority=100,
                prerendered=image,
            )
        ]


def _factory(config: Mapping[str, JSONValue]) -> CalendarProvider:
    path = config.get("path", str(DEFAULT_PATH))
    return CalendarProvider(path=path, view=config.get("view", "now"))


register_provider("calendar", _factory)
