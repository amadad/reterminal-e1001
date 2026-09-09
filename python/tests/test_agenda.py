from datetime import date, datetime

import pytest

from reterminal.family.calendar import CalendarItem, ParsedCalendar
from reterminal.family.agenda import calendar_days, upcoming_events, weekend_start
from reterminal.providers.calendar import CalendarProvider


def test_week_rolls_across_year_boundary_and_distinguishes_missing_days():
    parsed = ParsedCalendar(by_date={date(2026, 12, 31): []})
    days = calendar_days(parsed, date(2026, 12, 31), 7)
    assert days[0].available and not days[0].items
    assert days[-1].day == date(2027, 1, 6)
    assert not days[-1].available


@pytest.mark.parametrize("day, expected", [(8, 12), (12, 12), (13, 12), (14, 19)])
def test_weekend_advances_after_sunday(day, expected):
    assert weekend_start(date(2026, 9, day)) == date(2026, 9, expected)


def test_next_excludes_past_starts_sorts_times_and_preserves_tentative_labels():
    parsed = ParsedCalendar(by_date={
        date(2026, 9, 7): [CalendarItem("", "Past day", None)],
        date(2026, 9, 8): [
            CalendarItem("5:10pm", "Swim", "kids"),
            CalendarItem("", "Today all day", None),
            CalendarItem("9:00am", "Past start", None),
            CalendarItem("16:00", "Tentative birthday hold", None),
        ],
        date(2026, 9, 9): [CalendarItem("", "School photo day", None)],
    })
    events = upcoming_events(parsed, datetime(2026, 9, 8, 15, 30))
    assert [item.label for _, item in events] == [
        "Tentative birthday hold", "Swim", "School photo day",
    ]
    assert upcoming_events(parsed, datetime(2026, 9, 10)) == []


def test_views_have_distinct_scene_ids_and_advance_without_a_file_write(tmp_path, monkeypatch):
    path = tmp_path / "calendar.md"
    path.write_text("## 2026-09-08 Tue\n- 4:00pm Practice\n## 2026-09-09 Wed\n- 8:00am School\n")

    class Clock(datetime):
        current = datetime(2026, 9, 8, 15)

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr("reterminal.providers.calendar.datetime", Clock)
    providers = [CalendarProvider(path, view=view) for view in ("now", "week", "next", "weekend")]
    scenes = [provider.fetch()[0] for provider in providers]
    assert len({scene.id for scene in scenes}) == 4
    before = scenes[2].prerendered.tobytes()
    Clock.current = datetime(2026, 9, 8, 17)
    assert providers[2].fetch()[0].prerendered.tobytes() != before
    assert all(scene.prerendered.mode == "1" for scene in scenes)
    assert all(scene.prerendered.size == (800, 480) for scene in scenes)


def test_invalid_calendar_view_fails_at_configuration_time(tmp_path):
    with pytest.raises(ValueError, match="view"):
        CalendarProvider(tmp_path / "calendar.md", view="typo")


def test_now_distinguishes_an_empty_tomorrow_from_missing_data(tmp_path, monkeypatch):
    path = tmp_path / "calendar.md"
    today = date.today()
    path.write_text(f"## {today.isoformat()}\n")
    flags = []
    from reterminal.providers.calendar import render_calendar

    def capture(*args, **kwargs):
        flags.append(kwargs["tomorrow_available"])
        return render_calendar(*args, **kwargs)

    monkeypatch.setattr("reterminal.providers.calendar.render_calendar", capture)
    provider = CalendarProvider(path)
    provider.fetch()
    from datetime import timedelta
    path.write_text(path.read_text() + f"\n## {(today + timedelta(days=1)).isoformat()}\n")
    provider.fetch()
    assert flags == [False, True]


@pytest.mark.parametrize("view", ["now", "week", "next", "weekend", "prepare"])
def test_expired_export_is_never_described_as_nothing_scheduled(tmp_path, monkeypatch, view):
    path = tmp_path / "calendar.md"
    path.write_text("## 2020-01-01 Wed\n- Old event\n")
    notices = []
    from reterminal.render.kitchen import render_notice

    def capture(title, message, detail=None):
        notices.append(message)
        return render_notice(title, message, detail)

    monkeypatch.setattr("reterminal.providers.calendar.render_notice", capture)
    CalendarProvider(path, view=view).fetch()
    assert notices == ["calendar needs an update"]


@pytest.mark.parametrize("view", ["now", "week", "next", "weekend", "prepare"])
def test_calendar_typography_stays_on_panel_without_overlapping_text(tmp_path, monkeypatch, view):
    from datetime import timedelta
    from PIL import ImageDraw

    today = date.today()
    path = tmp_path / "calendar.md"
    path.write_text("\n".join(
        f"## {(today + timedelta(days=offset)).isoformat()}\n"
        "- 9:00am School parent meeting and welcome for the new year\n"
        "- 5:10pm Swimming lessons for the whole family\n"
        "- 6:00pm A very long event name that must wrap without shrinking the text\n"
        for offset in range(10)
    ))
    boxes = []
    original = ImageDraw.ImageDraw.text

    def record(draw, xy, text, *args, **kwargs):
        box = draw.textbbox(xy, text, font=kwargs.get("font"))
        boxes.append((text, box))
        return original(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    CalendarProvider(path, view=view).fetch()
    for index, (text, (left, top, right, bottom)) in enumerate(boxes):
        assert 0 <= left < right <= 800 and 0 <= top < bottom <= 480, text
        for other, (x0, y0, x1, y1) in boxes[index + 1:]:
            assert right <= x0 or x1 <= left or bottom <= y0 or y1 <= top, (text, other)


def test_structured_calendar_preserves_semantics_and_exclusive_event_end(tmp_path):
    import json
    from reterminal.family.calendar import parse_calendar
    from reterminal.family.agenda import remaining_today

    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({
        "timezone": "America/New_York", "checked_at": "2026-09-08T15:30:00-04:00",
        "start_date": "2026-09-08", "end_date": "2026-09-10",
        "events": [
            {"id": "ongoing", "summary": "Practice", "start": "2026-09-08T19:00:00Z",
             "end": "2026-09-08T20:00:00Z", "status": "tentative", "location": "School field"},
            {"id": "finished", "summary": "Earlier", "start": "2026-09-08T13:00:00Z", "end": "2026-09-08T14:00:00Z"},
            {"summary": "All day", "start": "2026-09-08", "end": "2026-09-10"},
            {"summary": "Cancelled", "status": "cancelled"},
        ],
    }))
    parsed = parse_calendar(path)
    assert parsed.checked_at.isoformat() == "2026-09-08T15:30:00-04:00"
    item = parsed.by_date[date(2026, 9, 8)][0]
    assert (item.event_id, item.time, item.status, item.location) == ("ongoing", "3:00pm", "tentative", "School field")
    assert item.ends.hour == 16 and item.timezone == "America/New_York"
    assert [item.label for item in remaining_today(parsed.by_date[date(2026, 9, 8)], datetime(2026, 9, 8, 15, 30))] == ["All day", "Practice"]
    assert [item.label for item in parsed.by_date[date(2026, 9, 9)]] == ["All day"]
    assert parsed.by_date[date(2026, 9, 10)] == []
    assert all(event.event_id != "ongoing" for _, event in upcoming_events(parsed, datetime(2026, 9, 8, 15, 30)))


def test_untimed_markdown_does_not_invent_finish_times():
    from reterminal.family.agenda import remaining_today
    items = [CalendarItem("9:00am", "Unknown duration", None)]
    assert remaining_today(items, datetime(2026, 9, 8, 15)) == items


def test_calendar_empty_today_and_source_stamp_are_truthful(tmp_path, monkeypatch):
    import json
    from PIL import ImageDraw

    today = date.today()
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({"timezone": "America/New_York", "checked_at": f"{today}T09:00:00-04:00",
                                "start_date": str(today), "end_date": str(today), "events": []}))
    texts = []
    original = ImageDraw.ImageDraw.text

    def record(draw, xy, text, *args, **kwargs):
        texts.append(text)
        return original(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    CalendarProvider(path).fetch()
    assert "Nothing else today." in texts
    assert "Calendar unavailable" in texts
    assert any("Source checked" in text and "9:00AM" in text for text in texts)
    assert not any("rendered" in text.lower() for text in texts)


@pytest.mark.parametrize("events", [None, {}, ["bad"], [{"summary": [], "start": "2026-09-09"}]])
def test_malformed_structured_calendar_is_an_explicit_error(tmp_path, events):
    import json
    from reterminal.family.calendar import parse_calendar
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({"timezone": "America/New_York", "checked_at": "2026-09-08T09:00:00-04:00",
                                "start_date": "2026-09-08", "end_date": "2026-09-11", "events": events}))
    with pytest.raises(ValueError):
        parse_calendar(path)


def test_next_deduplicates_future_multi_day_events_and_omits_underway_all_day(tmp_path):
    import json
    from reterminal.family.calendar import parse_calendar
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({"timezone": "America/New_York", "checked_at": "2026-09-08T09:00:00-04:00",
                                "start_date": "2026-09-08", "end_date": "2026-09-11", "events": [
        {"id": "underway", "summary": "Underway", "start": "2026-09-08", "end": "2026-09-10"},
        {"id": "future", "summary": "Future", "start": "2026-09-09", "end": "2026-09-12"},
    ]}))
    events = upcoming_events(parse_calendar(path), datetime(2026, 9, 8, 15))
    assert [(day, event.event_id) for day, event in events] == [(date(2026, 9, 9), "future")]
