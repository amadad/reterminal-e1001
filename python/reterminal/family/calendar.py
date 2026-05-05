"""Parser for `calendar.md` (## Today / ## Tomorrow sections).

Line grammar (per CONVENTIONS.md):

    - HH:MM[am|pm] Label [@who]

Examples:
    - 9:30am Piano [@kid1]
    - 12:00pm Family lunch
    - 4:00pm Baseball practice [@kid2]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PATH = Path.home() / "reterminal-content" / "family" / "calendar.md"

TIME_RE = re.compile(r"^(\d{1,2}(?::\d{2})?(?:am|pm)?)\s+(.*)$", re.IGNORECASE)
WHO_RE = re.compile(r"\[@([^\]]+)\]\s*$")


@dataclass(frozen=True)
class CalendarItem:
    time: str
    label: str
    who: str | None


def _parse_line(raw: str) -> CalendarItem | None:
    line = raw.strip()
    if not line.startswith("- "):
        return None
    body = line[2:].strip()
    if not body:
        return None
    who = None
    m_who = WHO_RE.search(body)
    if m_who:
        who = m_who.group(1).strip().lower()
        body = body[: m_who.start()].strip()
    m_time = TIME_RE.match(body)
    if m_time:
        time = m_time.group(1)
        label = m_time.group(2).strip()
    else:
        time = ""
        label = body
    return CalendarItem(time=time, label=label, who=who)


def parse_calendar(path: Path) -> tuple[list[CalendarItem], list[CalendarItem]]:
    today: list[CalendarItem] = []
    tomorrow: list[CalendarItem] = []
    section: str | None = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("## "):
            name = line[3:].strip().lower()
            section = name if name in {"today", "tomorrow"} else None
            continue
        if section is None:
            continue
        item = _parse_line(line)
        if item is None:
            continue
        (today if section == "today" else tomorrow).append(item)
    return today, tomorrow
