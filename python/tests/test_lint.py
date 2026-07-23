"""Tests for the per-provider markdown linters.

The renderers are deliberately lenient — they drop unparseable lines so a
typo can't crash the kitchen display. These tests pin down the *opposite*
behavior in `reterminal lint`: every line the renderer would silently
ignore must surface as a LintIssue.
"""

from __future__ import annotations

from pathlib import Path

from reterminal.providers.lint import (
    lint_activities,
    lint_calendar,
    lint_camps,
    lint_events,
    lint_manifest_files,
    lint_missions,
    lint_quest,
    lint_trip,
    manifest_lint_specs,
)
from reterminal.providers.manifest import FeedManifest, ProviderEntry


def _w(path: Path, body: str) -> Path:
    path.write_text(body)
    return path


def test_calendar_lint_clean(tmp_path: Path):
    md = _w(
        tmp_path / "calendar.md",
        "## 2026-05-08 Fri\n\n"
        "- 9:30am Piano [@kid1]\n"
        "- 12:00pm Family lunch\n"
        "- 4:00pm Baseball practice (Ammar)\n"
        "- All-day field trip\n"  # no time — loose grammar, not an issue
        "\n## Notes\n- ignored, not a rendered section\n",
    )
    assert lint_calendar(md) == []


def test_calendar_lint_flags_legacy_today_header(tmp_path: Path):
    md = _w(
        tmp_path / "calendar.md",
        "## Today\n- 9:30am Piano\n## Tomorrow\n- 4:00pm Soccer\n",
    )
    issues = lint_calendar(md)
    assert len(issues) == 2
    assert all("retired" in i.reason for i in issues)


def test_calendar_lint_flags_non_bullet(tmp_path: Path):
    md = _w(
        tmp_path / "calendar.md",
        "## 2026-05-08\nthis is prose, not a bullet\n- 9:30am Piano\n",
    )
    issues = lint_calendar(md)
    assert any("expected `- ` bullet" in i.reason for i in issues)


def test_events_lint_clean(tmp_path: Path):
    md = _w(
        tmp_path / "events.md",
        "## Upcoming\n"
        "- 2026-05-16 Cradle Con [event]\n"
        "- 2026-05-22 Maryland [trip]\n",
    )
    assert lint_events(md) == []


def test_events_lint_flags_bad_date(tmp_path: Path):
    md = _w(
        tmp_path / "events.md",
        "## Upcoming\n- May 16 Cradle Con [event]\n- 2026-05-22 Maryland [trip]\n",
    )
    issues = lint_events(md)
    assert len(issues) == 1
    assert "ISO date" in issues[0].reason


def test_activities_lint_recent_requires_date(tmp_path: Path):
    md = _w(
        tmp_path / "activities.md",
        "## Recent\n- 2026-04-24 Princess Bride [movie]\n- Undated thing [movie]\n"
        "## Queue\n- Stranger Things [series]\n- Back to the Future [movie]\n",
    )
    issues = lint_activities(md)
    assert len(issues) == 1
    assert "recent items require ISO date" in issues[0].reason


def test_missions_lint_clean(tmp_path: Path):
    md = _w(
        tmp_path / "missions.md",
        "## Active\n\n"
        "### Laila\n"
        "kind: project\n"
        "title: STEAM Fair\n"
        "progress: 1 / 4 weeks\n"
        "next: pick a problem\n",
    )
    assert lint_missions(md) == []


def test_missions_lint_flags_unknown_kind(tmp_path: Path):
    md = _w(
        tmp_path / "missions.md",
        "## Active\n\n"
        "### Laila\n"
        "kind: quest\n"
        "title: STEAM Fair\n"
        "progress: 1 / 4 weeks\n"
        "next: pick a problem\n",
    )
    issues = lint_missions(md)
    assert any("unknown kind 'quest'" in i.reason for i in issues)


def test_missions_lint_flags_missing_keys(tmp_path: Path):
    md = _w(
        tmp_path / "missions.md",
        "## Active\n\n"
        "### Hasan\n"
        "kind: habit\n"
        "title: Reading\n",  # missing progress + next
    )
    issues = lint_missions(md)
    assert any("missing required keys" in i.reason for i in issues)
    assert any("progress" in i.reason and "next" in i.reason for i in issues)


def test_missions_lint_flags_unknown_key(tmp_path: Path):
    md = _w(
        tmp_path / "missions.md",
        "## Active\n\n"
        "### Hasan\n"
        "kind: habit\n"
        "title: Reading\n"
        "progress: 0 days\n"
        "next: read a chapter\n"
        "stretch: read two chapters\n",
    )
    issues = lint_missions(md)
    assert any("unknown key 'stretch'" in i.reason for i in issues)


def test_camps_lint_requires_schedule_rows(tmp_path: Path):
    md = _w(tmp_path / "camps.md", "# Summer\n\nNo schedule yet.\n")
    issues = lint_camps(md)
    assert [issue.reason for issue in issues] == ["no camp schedule rows found"]


def test_camps_lint_rejects_invalid_week(tmp_path: Path):
    md = _w(
        tmp_path / "camps.md",
        "| Week | Kids | Laila | Notes |\n"
        "|---|---|---|---|\n"
        "| Someday | Sailing | Camp Rock | private |\n",
    )
    issues = lint_camps(md)
    assert len(issues) == 1
    assert "invalid camp week" in issues[0].reason


def test_quest_lint_uses_display_block_contract(tmp_path: Path):
    md = _w(
        tmp_path / "quest.md",
        "## Kitchen Display\n"
        "- **Title:** Build It\n"
        "- **Deck:** Try one change.\n"
        "- **Spark:** Draw it.\n"
        "- **Build:** Make it.\n"
        "- **Guide:** Explain it.\n"
        "- **Valid until:** 2026-07-30\n",
    )
    issues = lint_quest(md)
    assert len(issues) == 1
    assert "dinner" in issues[0].reason


def test_trip_lint_rejects_invalid_start_date(tmp_path: Path):
    md = _w(
        tmp_path / "trip.md",
        "## Kitchen Display\n"
        "- **Title:** Yellowstone\n"
        "- **Dates:** Aug 24-30\n"
        "- **Starts:** soon\n"
        "- **Route:** Jackson | Teton\n"
        "- **Next:** Verify lodging.\n"
        "- **Rule:** Protect the reset.\n"
        "- **Reviewed:** 2026-07-10\n",
    )
    issues = lint_trip(md)
    assert len(issues) == 1
    assert "ISO date" in issues[0].reason


def test_manifest_lint_specs_maps_multi_source_provider(tmp_path: Path):
    events = tmp_path / "events.md"
    queue = tmp_path / "activities.md"
    manifest = FeedManifest(
        providers=[
            ProviderEntry(
                type="comingup",
                config={"events": str(events), "queue": str(queue)},
                slot=2,
            ),
            ProviderEntry(type="photo", config={"path": str(tmp_path / "photos")}, slot=3),
        ]
    )

    assert manifest_lint_specs(manifest) == [("events", events), ("activities", queue)]


def test_lint_manifest_reports_missing_file(tmp_path: Path):
    issues = lint_manifest_files([("calendar", tmp_path / "nope.md")])
    assert len(issues) == 1
    assert issues[0].reason == "source file missing"


def test_calendar_strip_emoji_drops_pictographs():
    from reterminal.providers.calendar import _strip_emoji

    assert _strip_emoji("🏟️ Baseball Practice") == "Baseball Practice"
    assert _strip_emoji("⚾ Baseball - NSMS") == "Baseball - NSMS"
    assert _strip_emoji("🩰 Ballet (Laila)") == "Ballet (Laila)"
    # Plain text passes through.
    assert _strip_emoji("Register for Dance") == "Register for Dance"
