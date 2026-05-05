"""Parser for `missions.md` (## Active section, per-person ### Name blocks).

Each mission is a person heading followed by a key/value block:

    ### Laila
    kind: project | habit | goal | milestone
    title: short, concrete
    progress: kind-specific (`N / M weeks`, `N days`, `N / M`)
    streak: optional 0/1 sequence for habit kind
    next: the single next action

Helpers `parse_fraction` and `parse_days` extract numbers from `progress`
strings; they are public so non-render consumers (briefs, dashboards) can
reuse the same shape rules the renderer follows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_PATH = Path.home() / "reterminal-content" / "family" / "missions.md"

_KEYVAL = re.compile(r"^([a-z_]+):\s*(.*)$")
_NUM_OF_NUM = re.compile(r"(\d+)\s*/\s*(\d+)")
_DAYS_RE = re.compile(r"(\d+)\s*days?")


@dataclass(slots=True)
class Mission:
    who: str
    kind: str = ""
    title: str = ""
    progress: str = ""
    streak: list[int] = field(default_factory=list)
    next_action: str = ""


def parse_missions(path: Path) -> list[Mission]:
    missions: list[Mission] = []
    current: Mission | None = None
    in_active = False
    for raw in path.read_text().splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            in_active = line[3:].strip().lower() == "active"
            continue
        if not in_active:
            continue
        if line.startswith("### "):
            if current:
                missions.append(current)
            current = Mission(who=line[4:].strip())
            continue
        if current is None:
            continue
        m = _KEYVAL.match(line.strip())
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "kind":
            current.kind = val
        elif key == "title":
            current.title = val
        elif key == "progress":
            current.progress = val
        elif key == "streak":
            current.streak = [int(x) for x in val.split() if x in {"0", "1"}]
        elif key == "next":
            current.next_action = val
    if current:
        missions.append(current)
    return missions


def parse_fraction(s: str) -> tuple[int, int] | None:
    """Extract `N / M` from a progress string, e.g. `1 / 4 weeks` → (1, 4)."""
    m = _NUM_OF_NUM.search(s)
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_days(s: str) -> int | None:
    """Extract `N days` from a progress string, e.g. `7 days` → 7."""
    m = _DAYS_RE.search(s)
    return int(m.group(1)) if m else None
