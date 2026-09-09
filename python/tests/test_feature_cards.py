from __future__ import annotations

from datetime import date
import os
from pathlib import Path

import pytest

from reterminal.encoding import pil_to_raw
from reterminal.providers.features import (
    QuestProvider,
    parse_quest,
    parse_trip,
    render_quest,
    render_trip,
)


QUEST = """\
# Family Quest

Private prose that must not enter the display model.

## Kitchen Display

- **Title:** The One-Change Challenge
- **Deck:** Make it. Test it. Change one thing.
- **Spark:** Draw a machine with one moving part.
- **Build:** Make something, test it, and change one thing.
- **Guide:** Teach someone why your change worked.
- **Dinner:** What changed after testing?
- **Valid until:** 2026-07-26

## Notes

Ignored.
"""


TRIP = """\
# Private trip plan

Booking details that must not enter the display model.

## Kitchen Display

- **Title:** Yellowstone
- **Dates:** Aug 24–30
- **Starts:** 2026-08-24
- **Route:** Jackson | Teton | Yellowstone | Gardiner
- **Next:** Verify family lodging by Jul 29.
- **Rule:** One anchor. One optional add-on. Protect the reset.
- **Reviewed:** 2026-07-10

## Locked Bookings

Never rendered.
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def test_parse_quest_reads_only_kitchen_display(tmp_path: Path):
    quest = parse_quest(_write(tmp_path, "quest.md", QUEST))

    assert quest.title == "The One-Change Challenge"
    assert quest.deck == "Make it. Test it. Change one thing."
    assert quest.levels == (
        ("SPARK", "Draw a machine with one moving part."),
        ("BUILD", "Make something, test it, and change one thing."),
        ("GUIDE", "Teach someone why your change worked."),
    )
    assert quest.dinner == "What changed after testing?"
    assert quest.valid_until == date(2026, 7, 26)
    assert "Private prose" not in repr(quest)


def test_parse_trip_reads_safe_projection(tmp_path: Path):
    trip = parse_trip(_write(tmp_path, "trip.md", TRIP))

    assert trip.title == "Yellowstone"
    assert trip.starts == date(2026, 8, 24)
    assert trip.route == ("Jackson", "Teton", "Yellowstone", "Gardiner")
    assert trip.next_action == "Verify family lodging by Jul 29."
    assert "Booking details" not in repr(trip)


def test_missing_required_display_field_fails_closed(tmp_path: Path):
    path = _write(
        tmp_path,
        "quest.md",
        "## Kitchen Display\n- **Title:** Incomplete\n",
    )

    with pytest.raises(ValueError, match="missing Kitchen Display fields"):
        parse_quest(path)


def test_feature_renderers_are_native_monochrome_and_deterministic(tmp_path: Path):
    quest_path = _write(tmp_path, "quest.md", QUEST)
    trip_path = _write(tmp_path, "trip.md", TRIP)
    quest = parse_quest(quest_path)
    trip = parse_trip(trip_path)

    quest_a = render_quest(quest)
    quest_b = render_quest(quest)
    trip_image = render_trip(trip, today=date(2026, 7, 23))

    assert quest_a.mode == trip_image.mode == "1"
    assert quest_a.size == trip_image.size == (800, 480)
    assert pil_to_raw(quest_a) == pil_to_raw(quest_b)
    assert {value for _, value in quest_a.getcolors()} == {0, 255}
    assert {value for _, value in trip_image.getcolors()} == {0, 255}


def test_feature_provider_bitmap_does_not_depend_on_file_mtime(tmp_path: Path):
    path = _write(tmp_path, "quest.md", QUEST)
    provider = QuestProvider(path=path)
    first = provider.fetch()[0].prerendered
    os.utime(path, (2_000_000_000, 2_000_000_000))
    second = provider.fetch()[0].prerendered

    assert first is not None and second is not None
    assert pil_to_raw(first) == pil_to_raw(second)


def test_trip_countdown_changes_with_date(tmp_path: Path):
    trip = parse_trip(_write(tmp_path, "trip.md", TRIP))

    before = pil_to_raw(render_trip(trip, today=date(2026, 7, 23)))
    next_day = pil_to_raw(render_trip(trip, today=date(2026, 7, 24)))

    assert before != next_day


@pytest.mark.parametrize("kind, body", [("quest", QUEST), ("trip", TRIP)])
def test_seasonal_cards_fall_back_and_watch_both_sources(tmp_path, kind, body):
    from reterminal.providers.manifest import FeedManifest, build_providers
    path = _write(tmp_path, f"{kind}.md", body)
    calendar = _write(tmp_path, "calendar.md", f"## {date.today()}\n")
    manifest = FeedManifest.from_dict({"providers": [{
        "type": kind, "path": str(path), "slot": 2,
        "fallback": {"type": "calendar", "path": str(calendar), "view": "prepare"},
    }]})
    assert manifest.providers[0].source_paths() == [path, calendar]
    provider = build_providers(manifest)[0]
    scene = provider.fetch()[0]
    assert scene.id == "calendar-prepare" and scene.preferred_slot == 2
    path.write_text("Invalid card")
    assert provider.fetch()[0].id == "calendar-prepare"
    path.unlink()
    assert provider.fetch()[0].id == "calendar-prepare"


def test_trip_expiry_is_explicit_and_inclusive(tmp_path, monkeypatch):
    from reterminal.providers.features import TripProvider

    path = _write(tmp_path, "trip.md", TRIP.replace("- **Reviewed:**", "- **Valid until:** 2026-08-30\n- **Reviewed:**"))
    assert parse_trip(path).valid_until == date(2026, 8, 30)

    class Clock(date):
        current = date(2026, 8, 30)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr("reterminal.providers.features.date", Clock)
    provider = TripProvider(path, omit_unavailable=True)
    assert len(provider.fetch()) == 1
    Clock.current = date(2026, 8, 31)
    assert provider.fetch() == []
