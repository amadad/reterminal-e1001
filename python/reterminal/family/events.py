"""Parser for `events.md` (## Upcoming section).

Line grammar (per CONVENTIONS.md):

    - YYYY-MM-DD Label [tag]

Tags are free-form strings; the display maps them to icon shapes, but
that's a renderer concern — `Event` itself just holds the raw tag.
Past events are filtered out at parse time so callers always see future
proximity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


DEFAULT_PATH = Path.home() / "reterminal-content" / "family" / "events.md"

ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(.*)$")
TAG_RE = re.compile(r"\[([^\]]+)\]\s*$")


@dataclass(frozen=True)
class Event:
    on: date
    label: str
    tag: str | None

    @property
    def days_until(self) -> int:
        return (self.on - date.today()).days


def parse_events(path: Path) -> list[Event]:
    events: list[Event] = []
    in_section = False
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("## "):
            in_section = line[3:].strip().lower() == "upcoming"
            continue
        if not in_section or not line.startswith("- "):
            continue
        body = line[2:].strip()
        tag = None
        m_tag = TAG_RE.search(body)
        if m_tag:
            tag = m_tag.group(1).strip().lower()
            body = body[: m_tag.start()].strip()
        m = ISO_DATE.match(body)
        if not m:
            continue
        y, mo, d, label = m.groups()
        events.append(Event(date(int(y), int(mo), int(d)), label.strip(), tag))
    events.sort(key=lambda e: e.on)
    return [e for e in events if e.days_until >= 0]
