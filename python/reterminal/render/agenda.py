"""Glanceable Week, Next, and Weekend compositions from calendar projections."""

import re
from datetime import date, datetime
from pathlib import Path

from reterminal.family.agenda import CalendarDay
from reterminal.family.calendar import CalendarItem
from reterminal.render.kitchen import (
    AGENDA_BODY, AGENDA_LABEL, AGENDA_LEADING, AGENDA_TITLE, DISPLAY, MARGIN, WIDTH,
    draw_kicker, draw_rule, draw_calendar_stamp, new_canvas, to_1bit,
)
from reterminal.render.layout import wrap_text


def _label(item: CalendarItem) -> str:
    # Keep calendar wording (including tentative/hold qualifiers); remove glyphs
    # the bundled text font cannot represent.
    text = re.sub("[\U0001f300-\U0001faff☀-➿️]+", "", item.label).strip()
    if item.status == "tentative" and "tentative" not in text.lower():
        text = "Tentative · " + text
    return f"{text} · {item.who.title()}" if item.who else text


def _when(item: CalendarItem) -> str:
    if item.ends is not None and item.starts is not None:
        return f"{item.time}–{item.ends:%-I:%M%p}"
    return item.time or "All day"


def _lines(draw, text, font, width, *, x, y, fill=0):
    lines = wrap_text(draw, text, font, width)
    height = AGENDA_LEADING if font == AGENDA_BODY else font.size + 6
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += height
    return y


def render_week(days: list[CalendarDay], *, source_path: Path, checked_at: datetime | None = None):
    img, draw = new_canvas()
    start, end = days[0].day, days[-1].day
    draw_kicker(draw, "Week", right=f"{start:%b %-d} – {end:%b %-d}".upper(), label_font=AGENDA_LABEL)
    # A full-width reading measure avoids seven tiny cards. Show the first
    # event on the first four scheduled days, and disclose omitted days.
    scheduled = [day for day in days if day.items or not day.available]
    cursor = 76
    shown = 0
    for day in scheduled:
        text = _label(day.items[0]) if day.items else "Calendar unavailable"
        width = WIDTH - MARGIN * 2
        lines = wrap_text(draw, text, AGENDA_BODY, width)
        needed = 28 + len(lines) * AGENDA_LEADING + 20
        if shown == 4 or cursor + needed > 414:
            break
        meta = day.day.strftime("%a %-d").upper()
        if day.items:
            meta += f" · {day.items[0].time or 'All day'}"
        draw.text((MARGIN, cursor), meta, font=AGENDA_LABEL, fill=0)
        _lines(draw, text, AGENDA_BODY, width, x=MARGIN, y=cursor + 28)
        cursor += needed
        draw_rule(draw, cursor - 12)
        shown += 1
    if not scheduled:
        _lines(draw, "Nothing scheduled in the next seven days.", AGENDA_BODY,
               WIDTH - MARGIN * 2, x=MARGIN, y=100)
    extra_events = sum(len(day.items) for day in days) - sum(bool(day.items) for day in scheduled[:shown])
    missing = sum(not day.available for day in days)
    if missing:
        footer = "Some calendar dates are unavailable."
    elif extra_events:
        footer = f"First event per day · {extra_events} more in calendar"
    else:
        footer = "First event on each scheduled day"
    draw.text((MARGIN, 418), footer, font=AGENDA_LABEL, fill=0)
    draw_calendar_stamp(draw, source_path, checked_at=checked_at)
    return to_1bit(img)


def render_next(events: list[tuple[date, CalendarItem]], *, now: datetime, source_path: Path, checked_at: datetime | None = None):
    img, draw = new_canvas()
    draw_kicker(draw, "Next", right=now.strftime("%a · %b %-d").upper(), label_font=AGENDA_LABEL)
    if not events:
        _lines(draw, "No upcoming starts in the exported calendar.", AGENDA_TITLE,
               WIDTH - MARGIN * 2, x=MARGIN, y=100)
    else:
        day, item = events[0]
        when = "TODAY" if day == now.date() else day.strftime("%A · %b %-d").upper()
        draw.text((MARGIN, 72), when, font=AGENDA_TITLE, fill=0)
        draw.text((MARGIN, 116), item.time or "COMING UP", font=DISPLAY, fill=0)
        label = _label(item)
        if len(wrap_text(draw, label, AGENDA_TITLE, WIDTH - MARGIN * 2)) > 5:
            label = "Open the family calendar for the full event title."
        label_bottom = _lines(draw, label, AGENDA_TITLE, WIDTH - MARGIN * 2,
                              x=MARGIN, y=194)
        cursor = max(308, label_bottom + 28)
        if len(events) > 1 and cursor < 360:
            draw_rule(draw, cursor)
            draw.text((MARGIN, cursor + 12), "AFTER THAT", font=AGENDA_LABEL, fill=0)
            other_day, other = events[1]
            text = f"{other_day:%a %-d} · {other.time or 'All day'} · {_label(other)}"
            lines = wrap_text(draw, text, AGENDA_BODY, WIDTH - MARGIN * 2)
            if cursor + 44 + len(lines) * AGENDA_LEADING <= 430:
                _lines(draw, text, AGENDA_BODY, WIDTH - MARGIN * 2, x=MARGIN, y=cursor + 44)
    draw_calendar_stamp(draw, source_path, checked_at=checked_at)
    return to_1bit(img)


def render_day_columns(
    days: list[CalendarDay],
    *,
    title: str,
    headings: tuple[str, str],
    source_path: Path | None,
    notice: str | None = None,
    checked_at: datetime | None = None,
):
    img, draw = new_canvas()
    draw_kicker(draw, title, right=f"{days[0].day:%b %-d} – {days[-1].day:%b %-d}".upper(), label_font=AGENDA_LABEL)
    width = (WIDTH - MARGIN * 3) // 2
    for index, day in enumerate(days):
        x = MARGIN + index * (width + MARGIN)
        draw.text((x, 70), headings[index], font=AGENDA_TITLE, fill=0)
        draw.text((x, 116), day.day.strftime("%A %-d"), font=AGENDA_LABEL, fill=0)
        draw_rule(draw, 150, x0=x, x1=x + width)
        cursor = 172
        if not day.available:
            _lines(draw, "Calendar unavailable", AGENDA_BODY, width, x=x, y=cursor)
        elif not day.items:
            _lines(draw, "Nothing else today." if day.remaining else "Nothing scheduled.", AGENDA_BODY, width, x=x, y=cursor)
        for item_index, item in enumerate(day.items):
            lines = wrap_text(draw, _label(item), AGENDA_BODY, width)
            needed = 30 + len(lines) * AGENDA_LEADING + 22
            limit = (410 if notice else 430) - (0 if item_index == len(day.items) - 1 else 26)
            if cursor + needed > limit:
                remaining = len(day.items) - item_index
                draw.text((x, cursor), f"+{remaining} more in calendar", font=AGENDA_LABEL, fill=0)
                break
            draw.text((x, cursor), _when(item), font=AGENDA_LABEL, fill=0)
            cursor = _lines(draw, _label(item), AGENDA_BODY, width, x=x, y=cursor + 30) + 22
    if notice:
        draw.text((MARGIN, 418), notice, font=AGENDA_LABEL, fill=0)
    draw_calendar_stamp(draw, source_path, checked_at=checked_at)
    return to_1bit(img)


def render_weekend(days: list[CalendarDay], *, source_path: Path, checked_at: datetime | None = None):
    return render_day_columns(days, title="Weekend", headings=("Saturday", "Sunday"), source_path=source_path, checked_at=checked_at)


def render_prepare(day: CalendarDay, *, source_path: Path, checked_at: datetime | None = None):
    """Surface tomorrow's source-backed details without inventing errands."""
    img, draw = new_canvas()
    draw_kicker(draw, "Tomorrow", right=day.day.strftime("%a · %b %-d").upper(), label_font=AGENDA_LABEL)
    if not day.available or not day.items:
        message = "Tomorrow's calendar is unavailable." if not day.available else "Nothing scheduled tomorrow."
        _lines(draw, message, AGENDA_TITLE, WIDTH - MARGIN * 2, x=MARGIN, y=90)
    else:
        item = day.items[0]
        draw.text((MARGIN, 76), item.time or "ALL-DAY ENTRY", font=DISPLAY if item.time else AGENDA_LABEL, fill=0)
        label = _label(item)
        if len(wrap_text(draw, label, AGENDA_TITLE, WIDTH - MARGIN * 2)) > 4:
            label = "Open the family calendar for the full event title."
        cursor = _lines(draw, label, AGENDA_TITLE, WIDTH - MARGIN * 2, x=MARGIN, y=150)
        if item.location:
            location = item.location
            if len(wrap_text(draw, location, AGENDA_BODY, WIDTH - MARGIN * 2)) > 2:
                location = "Location details in calendar"
            if cursor + 100 <= 410:
                _lines(draw, location, AGENDA_BODY, WIDTH - MARGIN * 2, x=MARGIN, y=cursor + 28)
        if len(day.items) > 1:
            draw.text((MARGIN, 418), f"First event · {len(day.items) - 1} more tomorrow", font=AGENDA_LABEL, fill=0)
    draw_calendar_stamp(draw, source_path, checked_at=checked_at)
    return to_1bit(img)
