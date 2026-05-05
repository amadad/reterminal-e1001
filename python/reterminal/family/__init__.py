"""Pure parsers + dataclasses for the four family-state markdown files.

The grammars are documented in `~/madad/family/CONVENTIONS.md` (or your own
family root). They live here rather than inside `reterminal.providers` so
non-display tools — morning briefs, recall CLIs, OC flows, Apple Shortcuts,
weekly digests — can import them without dragging in PIL or the render
pipeline.

Each submodule owns one file's grammar:

- `family.calendar`   → `## Today` / `## Tomorrow`, line `HH:MM Label [@who]`
- `family.missions`   → `## Active` blocks of `### Name` / `kind:` / `next:` …
- `family.events`     → `## Upcoming`, line `YYYY-MM-DD Label [tag]`
- `family.activities` → `## Recent` / `## Queue`, line `YYYY-MM-DD Label [tag]`

Parsers are pure: they take a `Path`, read it once, and return immutable
dataclasses. They never write back, never network, never raise on malformed
lines — unparseable lines are silently dropped (use `reterminal lint` to
surface them).
"""

from reterminal.family.activities import (
    Activity,
    parse_activities,
    parse_activity_line,
)
from reterminal.family.calendar import CalendarItem, parse_calendar
from reterminal.family.events import Event, parse_events
from reterminal.family.missions import (
    Mission,
    parse_days,
    parse_fraction,
    parse_missions,
)

__all__ = [
    "Activity",
    "CalendarItem",
    "Event",
    "Mission",
    "parse_activities",
    "parse_activity_line",
    "parse_calendar",
    "parse_days",
    "parse_events",
    "parse_fraction",
    "parse_missions",
]
