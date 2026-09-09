"""Parser for `calendar.md` (## YYYY-MM-DD Day sections).

Calendar is the only family-state file with date-relative semantics, so it
carries absolute dates as section headers. The renderer picks today and
tomorrow at render time from `date.today()`. This makes "the file is
stale" a visible failure (today's section is missing) rather than an
invisible one (Tuesday's events labeled as today's).

Section grammar:

    ## 2026-05-08 Fri     ← weekday suffix optional but recommended
    ## 2026-05-08

Line grammar:

    - HH:MM[am|pm] Label [@who]
    - HH Label                     ← time minutes optional
    - Label                        ← time optional (all-day / informal)
    - HH:MM Label (Name)           ← (Name) accepted as a who shortcut

`[@who]` may appear anywhere in the line; the first match wins. Lines
that don't parse get counted in `ParsedCalendar.dropped` so the renderer
can surface the count instead of swallowing them silently.

The retired `## Today` / `## Tomorrow` headers are detected and reported
via `legacy_headers`; the renderer shows a migration notice when the
file uses only the retired schema.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_PATH = Path.home() / "reterminal-content" / "family" / "calendar.md"

DATE_HEADER_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\s+\S+)?\s*$")
LEGACY_HEADER_RE = re.compile(r"^(today|tomorrow)\s*$", re.IGNORECASE)
TIME_RE = re.compile(r"^(\d{1,2}(?::\d{2})?(?:am|pm)?)\s+(.*)$", re.IGNORECASE)
WHO_RE = re.compile(r"\[@([^\]]+)\]")
PAREN_WHO_RE = re.compile(r"\s*\(([^)]+)\)\s*$")


@dataclass(frozen=True)
class CalendarItem:
    time: str
    label: str
    who: str | None
    starts: datetime | None = None
    ends: datetime | None = None
    timezone: str | None = None
    status: str | None = None
    location: str | None = None
    event_id: str | None = None
    start_date: date | None = None


@dataclass(frozen=True)
class ParsedCalendar:
    by_date: dict[date, list[CalendarItem]] = field(default_factory=dict)
    dropped: int = 0
    legacy_headers: bool = False
    checked_at: datetime | None = None
    timezone: str | None = None


def _parse_line(raw: str) -> CalendarItem | None:
    line = raw.strip()
    if not line.startswith("- "):
        return None
    body = line[2:].strip()
    if not body:
        return None
    who: str | None = None
    m_who = WHO_RE.search(body)
    if m_who:
        who = m_who.group(1).strip().lower()
        body = (body[: m_who.start()] + body[m_who.end():]).strip()
    else:
        m_paren = PAREN_WHO_RE.search(body)
        if m_paren:
            who = m_paren.group(1).strip().lower()
            body = body[: m_paren.start()].strip()
    m_time = TIME_RE.match(body)
    if m_time:
        return CalendarItem(time=m_time.group(1), label=m_time.group(2).strip(), who=who)
    return CalendarItem(time="", label=body, who=who)


def parse_calendar(path: Path) -> ParsedCalendar:
    if path.suffix == ".json":
        return parse_calendar_json(path)
    by_date: dict[date, list[CalendarItem]] = {}
    current: date | None = None
    dropped = 0
    legacy = False
    in_section = False
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("## "):
            header = line[3:].strip()
            m = DATE_HEADER_RE.match(header)
            if m:
                current = date.fromisoformat(m.group(1))
                in_section = True
                by_date.setdefault(current, [])
            else:
                if LEGACY_HEADER_RE.match(header):
                    legacy = True
                current = None
                in_section = False
            continue
        if not in_section or not line:
            continue
        if line.startswith("- "):
            item = _parse_line(line)
            if item is None:
                dropped += 1
                continue
            assert current is not None
            by_date[current].append(item)
        else:
            dropped += 1
    return ParsedCalendar(by_date=by_date, dropped=dropped, legacy_headers=legacy)


def events_for(parsed: ParsedCalendar, day: date) -> list[CalendarItem]:
    return parsed.by_date.get(day, [])


def parse_calendar_json(path: Path) -> ParsedCalendar:
    """Read a checked, date-bounded projection of calendar event records.

    Dates in the export range are inclusive; Google all-day event ends are
    exclusive. Missing or invalid records never turn into a claim of free time.
    """
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("calendar export must be an object")
    if not isinstance(data.get("events"), list):
        raise ValueError("calendar events must be a list")
    for key in ("timezone", "checked_at", "start_date", "end_date"):
        if not isinstance(data.get(key), str):
            raise ValueError(f"calendar {key} must be a string")
    timezone = data["timezone"]
    tz = ZoneInfo(timezone)
    checked_at = datetime.fromisoformat(data["checked_at"].replace("Z", "+00:00"))
    if checked_at.tzinfo is None:
        raise ValueError("calendar checked_at must include a timezone")
    start = date.fromisoformat(data["start_date"])
    end = date.fromisoformat(data["end_date"])
    if not 0 <= (end - start).days <= 366:
        raise ValueError("calendar export range must cover 1 to 367 days")
    by_date = {start + timedelta(days=i): [] for i in range((end - start).days + 1)}
    for event in data["events"]:
        if not isinstance(event, dict):
            raise ValueError("calendar event must be an object")
        if event.get("status") == "cancelled":
            continue
        for key in ("summary", "start"):
            if not isinstance(event.get(key), str):
                raise ValueError(f"calendar event {key} must be a string")
        for key in ("end", "status", "location", "id", "who"):
            if event.get(key) is not None and not isinstance(event[key], str):
                raise ValueError(f"calendar event {key} must be a string")
        label = event["summary"].strip()
        if not label:
            raise ValueError("calendar event requires a summary")
        raw_start, raw_end = event["start"], event.get("end")
        starts = ends = None
        if "T" in raw_start:
            starts = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
            if starts.tzinfo is None:
                raise ValueError("timed event must include a timezone")
            starts = starts.astimezone(tz)
            if raw_end:
                ends = datetime.fromisoformat(raw_end.replace("Z", "+00:00"))
                if ends.tzinfo is None:
                    raise ValueError("event end must include a timezone")
                ends = ends.astimezone(tz)
                if ends <= starts:
                    raise ValueError("event end must follow start")
            first = starts.date()
            last = (ends - timedelta(microseconds=1)).date() if ends else first
            clock = starts.strftime("%-I:%M%p").lower()
        else:
            first = date.fromisoformat(raw_start)
            last = date.fromisoformat(raw_end) - timedelta(days=1) if raw_end else first
            clock = ""
            if last < first:
                raise ValueError("all-day event end must follow start")
        item = CalendarItem(clock, label, event.get("who"), starts, ends, timezone,
                            event.get("status"), event.get("location"), event.get("id"), first)
        cursor = max(first, start)
        while cursor <= min(last, end):
            by_date[cursor].append(item)
            cursor += timedelta(days=1)
    return ParsedCalendar(by_date=by_date, checked_at=checked_at.astimezone(tz), timezone=timezone)
