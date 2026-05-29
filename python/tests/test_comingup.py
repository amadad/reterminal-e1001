"""Tests for the Coming Up provider (merges events + activities queue)."""

from __future__ import annotations

from pathlib import Path

from reterminal.providers.comingup import ComingUpProvider

EVENTS = "# Events\n\n## Upcoming\n\n- 2099-01-01 New Year [event]\n"
ACTIVITIES = (
    "# Activities\n\n## Recent\n\n- 2026-01-01 Old Movie [movie]\n\n"
    "## Queue\n\n- Scream [movie]\n- Solo Leveling [series]\n"
)


def _write(tmp_path: Path) -> tuple[Path, Path]:
    e = tmp_path / "events.md"
    e.write_text(EVENTS)
    a = tmp_path / "activities.md"
    a.write_text(ACTIVITIES)
    return e, a


def test_comingup_renders_with_both_sources(tmp_path: Path):
    e, a = _write(tmp_path)
    scenes = ComingUpProvider(events=e, queue=a).fetch()
    assert len(scenes) == 1
    assert scenes[0].id == "comingup"
    assert scenes[0].prerendered is not None


def test_comingup_tolerates_missing_one_source(tmp_path: Path):
    e, a = _write(tmp_path)
    # Only the queue file exists — events absent should not crash.
    scenes = ComingUpProvider(events=tmp_path / "gone.md", queue=a).fetch()
    assert scenes[0].prerendered is not None


def test_comingup_missing_both_renders_notice(tmp_path: Path):
    scenes = ComingUpProvider(
        events=tmp_path / "a.md", queue=tmp_path / "b.md"
    ).fetch()
    assert scenes[0].prerendered is not None  # "coming-up source missing" notice
