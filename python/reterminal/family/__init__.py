"""Pure parsers + dataclasses for the four family-state markdown files.

The grammars are documented in `~/madad/family/CONVENTIONS.md` (or your own
family root). They live here rather than inside `reterminal.providers` so
non-display tools — morning briefs, recall CLIs, OC flows, Apple Shortcuts,
weekly digests — can import them without dragging in PIL or the render
pipeline.

Each submodule owns one file's grammar:

- `family.calendar`   → `## YYYY-MM-DD [Day]`, line `HH:MM Label [@who]`
- `family.missions`   → `## Active` blocks of `### Name` / `kind:` / `next:` …
- `family.events`     → `## Upcoming`, line `YYYY-MM-DD Label [tag]`
- `family.activities` → `## Recent` / `## Queue`, line `YYYY-MM-DD Label [tag]`

Parsers are pure: they take a `Path`, read it once, and return immutable
dataclasses. They never write back, never network, never raise on malformed
lines — unparseable lines are silently dropped. `parse_calendar` additionally
returns a `dropped` count so the renderer can surface the silent loss; use
`reterminal lint` to identify which lines.
"""

from reterminal.family.activities import (
    Activity,
    parse_activities,
    parse_activity_line,
)
from reterminal.family.camps import Camp, parse_camps
from reterminal.family.calendar import (
    CalendarItem,
    ParsedCalendar,
    events_for,
    parse_calendar,
)
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
    "Camp",
    "Event",
    "Mission",
    "ParsedCalendar",
    "events_for",
    "parse_activities",
    "parse_activity_line",
    "parse_calendar",
    "parse_camps",
    "parse_days",
    "parse_events",
    "parse_fraction",
    "parse_missions",
]
