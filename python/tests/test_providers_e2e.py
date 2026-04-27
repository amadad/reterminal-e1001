"""End-to-end smoke tests for the kitchen-display providers.

Verifies that the four registered providers (calendar, missions, events,
activities) accept the documented config, return SceneSpec objects with
prerendered bitmaps of the right size and mode, and route through the
manifest registry as expected.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

import reterminal.providers  # noqa: F401  -- triggers provider registration
from reterminal.providers.activities import ActivitiesProvider
from reterminal.providers.calendar import CalendarProvider
from reterminal.providers.events import EventsProvider
from reterminal.providers.manifest import build_providers, load_manifest
from reterminal.providers.missions import MissionsProvider


WIDTH, HEIGHT = 800, 480


def _assert_bitmap(scene_image) -> None:
    assert isinstance(scene_image, Image.Image)
    assert scene_image.size == (WIDTH, HEIGHT)
    assert scene_image.mode == "1"


def _write(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


def test_missions_provider_renders(tmp_path: Path):
    md = _write(
        tmp_path / "missions.md",
        "## Active\n\n"
        "### Laila\n"
        "kind: project\n"
        "title: STEAM Fair\n"
        "progress: 1 / 4 weeks\n"
        "next: pick a problem\n",
    )
    scenes = MissionsProvider(path=md).fetch()
    assert len(scenes) == 1
    s = scenes[0]
    assert s.id == "missions"
    assert s.kind == "prerendered"
    assert s.preferred_slot == 1
    _assert_bitmap(s.prerendered)


def test_events_provider_renders(tmp_path: Path):
    md = _write(
        tmp_path / "events.md",
        "## Upcoming\n\n"
        "- 2099-01-01 New Year [event]\n"
        "- 2099-06-15 Camp [camp]\n",
    )
    scenes = EventsProvider(path=md).fetch()
    assert len(scenes) == 1
    s = scenes[0]
    assert s.id == "events"
    assert s.preferred_slot == 2
    _assert_bitmap(s.prerendered)


def test_activities_provider_renders(tmp_path: Path):
    md = _write(
        tmp_path / "activities.md",
        "## Recent\n\n"
        "- 2026-04-24 Movie Night [movie]\n\n"
        "## Queue\n\n"
        "- Back to the Future [movie]\n",
    )
    scenes = ActivitiesProvider(path=md).fetch()
    assert len(scenes) == 1
    s = scenes[0]
    assert s.id == "activities"
    assert s.preferred_slot == 3
    _assert_bitmap(s.prerendered)


def test_calendar_provider_renders(tmp_path: Path):
    md = _write(
        tmp_path / "calendar.md",
        "## Today\n\n"
        "- 9:30am Hasan piano [@hasan]\n"
        "- 12:00pm Family lunch\n\n"
        "## Tomorrow\n\n"
        "- 8:00am School\n",
    )
    scenes = CalendarProvider(path=md).fetch()
    assert len(scenes) == 1
    s = scenes[0]
    assert s.id == "calendar"
    assert s.preferred_slot == 0
    _assert_bitmap(s.prerendered)


def test_provider_returns_empty_when_file_missing(tmp_path: Path):
    missing = tmp_path / "absent.md"
    assert MissionsProvider(path=missing).fetch() == []
    assert EventsProvider(path=missing).fetch() == []
    assert ActivitiesProvider(path=missing).fetch() == []
    assert CalendarProvider(path=missing).fetch() == []


def test_manifest_builds_all_four_providers(tmp_path: Path):
    manifest_path = _write(
        tmp_path / "kitchen.json",
        json.dumps(
            {
                "providers": [
                    {"type": "calendar", "path": str(tmp_path / "calendar.md")},
                    {"type": "missions", "path": str(tmp_path / "missions.md")},
                    {"type": "events", "path": str(tmp_path / "events.md")},
                    {"type": "activities", "path": str(tmp_path / "activities.md")},
                ]
            }
        ),
    )
    providers = build_providers(load_manifest(manifest_path))
    assert [p.name for p in providers] == ["calendar", "missions", "events", "activities"]


def test_example_kitchen_display_manifest_resolves():
    """The shipped example file must reference only registered provider types."""
    example = Path(__file__).resolve().parent.parent / "examples" / "kitchen-display.json"
    providers = build_providers(load_manifest(example))
    assert len(providers) == 4
