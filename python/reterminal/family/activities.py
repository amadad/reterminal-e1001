"""Parser for `activities.md` (## Recent / ## Queue sections).

Line grammar (per CONVENTIONS.md):

    - YYYY-MM-DD Label [tag]   (Recent — date required)
    - Label [tag]               (Queue — date optional)

Recent items are returned newest-first by date; queue items keep their
written order (the first item is the implicit hero / "what's next").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


DEFAULT_PATH = Path.home() / "reterminal-content" / "family" / "activities.md"

ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(.*)$")
TAG_RE = re.compile(r"\[([^\]]+)\]\s*$")


@dataclass(frozen=True)
class Activity:
    on: date | None
    label: str
    tag: str | None


def parse_activity_line(line: str) -> Activity | None:
    body = line[2:].strip() if line.startswith("- ") else line.strip()
    if not body:
        return None
    tag = None
    m = TAG_RE.search(body)
    if m:
        tag = m.group(1)
        body = body[: m.start()].strip()
    m = ISO_DATE.match(body)
    if m:
        y, mo, d, label = m.groups()
        return Activity(date(int(y), int(mo), int(d)), label.strip(), tag)
    return Activity(None, body, tag)


def parse_activities(path: Path) -> tuple[list[Activity], list[Activity]]:
    recent: list[Activity] = []
    queue: list[Activity] = []
    section: str | None = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("## "):
            name = line[3:].strip().lower()
            section = name if name in {"recent", "queue"} else None
            continue
        if section is None or not line.startswith("- "):
            continue
        item = parse_activity_line(line)
        if item is None:
            continue
        (recent if section == "recent" else queue).append(item)
    recent.sort(key=lambda a: a.on or date.min, reverse=True)
    return recent, queue
