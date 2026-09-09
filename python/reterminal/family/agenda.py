"""Date-relative views of the exported family calendar; no network or PIL."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from reterminal.family.calendar import CalendarItem, ParsedCalendar


def _minutes(label: str) -> int | None:
    for pattern in ("%I:%M%p", "%I%p", "%H:%M", "%H"):
        try:
            value = datetime.strptime(label, pattern)
            return value.hour * 60 + value.minute
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class CalendarDay:
    day: date
    items: tuple[CalendarItem, ...]
    available: bool
    remaining: bool = False


def calendar_days(parsed: ParsedCalendar, start: date, count: int) -> list[CalendarDay]:
    days = []
    for offset in range(count):
        day = start + timedelta(days=offset)
        items = sorted(parsed.by_date.get(day, []), key=lambda item: _minutes(item.time) or 0)
        days.append(CalendarDay(day, tuple(items), day in parsed.by_date))
    return days


def weekend_start(today: date) -> date:
    # Saturday/Sunday share the same weekend; Monday advances to the next one.
    return today + timedelta(days=5 - today.weekday())


def upcoming_events(parsed: ParsedCalendar, now: datetime) -> list[tuple[date, CalendarItem]]:
    events = []
    seen = set()
    today = now.date()
    minute = now.hour * 60 + now.minute
    for day in sorted(parsed.by_date):
        if day < today:
            continue
        for item in sorted(parsed.by_date[day], key=lambda item: _minutes(item.time) or 0):
            identity = item.event_id or id(item)
            if identity in seen:
                continue
            if item.start_date is not None and item.starts is None and item.start_date <= today:
                continue
            if item.starts is not None:
                clock_now = now.astimezone(item.starts.tzinfo) if now.tzinfo else now.replace(tzinfo=item.starts.tzinfo)
                if item.starts < clock_now:
                    continue
            starts = _minutes(item.time)
            # Today's all-day items are already underway and remain on Now.
            # The export has no end times, so Next describes starts, not availability.
            if day == today and (starts is None or starts < minute):
                continue
            seen.add(identity)
            events.append((day, item))
    return events


def remaining_today(items: list[CalendarItem], now: datetime) -> list[CalendarItem]:
    """Keep ongoing events when their end is known; never invent an end time."""
    result = []
    for item in items:
        if item.ends is not None:
            local_now = now.astimezone(item.ends.tzinfo) if now.tzinfo else now.replace(tzinfo=item.ends.tzinfo)
            if item.ends <= local_now:
                continue
        # Markdown has only starts. Retain those entries; a past start alone
        # cannot tell us that an event has finished.
        result.append(item)
    return sorted(result, key=lambda item: (item.start_date or now.date(), _minutes(item.time) or 0))
