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

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

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


@dataclass(frozen=True)
class ParsedCalendar:
    by_date: dict[date, list[CalendarItem]] = field(default_factory=dict)
    dropped: int = 0
    legacy_headers: bool = False


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
