"""Tests for `reterminal brief` — the sample family-state consumer."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from reterminal.cli.app import app


runner = CliRunner()


def _write_manifest(tmp_path: Path, files: dict[str, Path]) -> Path:
    manifest = {
        "providers": [
            {"type": kind, "path": str(path), "slot": slot}
            for slot, (kind, path) in enumerate(files.items())
        ]
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest))
    return p


def _seed_family(tmp_path: Path) -> dict[str, Path]:
    cal = tmp_path / "calendar.md"
    cal.write_text(
        "## Today\n"
        "- 9:30am Piano [@kid1]\n"
        "- 12:00pm Family lunch\n"
        "## Tomorrow\n"
        "- 8:00am School\n"
    )
    miss = tmp_path / "missions.md"
    miss.write_text(
        "## Active\n\n"
        "### Laila\n"
        "kind: project\n"
        "title: STEAM Fair\n"
        "progress: 1 / 4 weeks\n"
        "next: pick a problem\n"
    )
    ev = tmp_path / "events.md"
    ev.write_text(
        "## Upcoming\n"
        "- 2099-12-31 Far future trip [trip]\n"
    )
    act = tmp_path / "activities.md"
    act.write_text(
        "## Recent\n"
        "- 2026-04-24 Princess Bride [movie]\n"
        "## Queue\n"
        "- Dune 2021 [movie]\n"
        "- Stranger Things [series]\n"
    )
    return {"calendar": cal, "missions": miss, "events": ev, "activities": act}


def test_brief_text_output(tmp_path: Path):
    files = _seed_family(tmp_path)
    feed = _write_manifest(tmp_path, files)
    result = runner.invoke(app, ["brief", "--feed", str(feed)])
    assert result.exit_code == 0, result.output
    assert "TODAY (2)" in result.output
    assert "Piano" in result.output
    assert "TOMORROW (1)" in result.output
    assert "MISSIONS" in result.output
    assert "Laila: STEAM Fair → pick a problem" in result.output
    assert "NEXT EVENT" in result.output
    assert "Far future trip" in result.output
    assert "WATCHING NEXT" in result.output
    assert "Dune 2021" in result.output


def test_brief_json_output(tmp_path: Path):
    files = _seed_family(tmp_path)
    feed = _write_manifest(tmp_path, files)
    result = runner.invoke(app, ["brief", "--feed", str(feed), "--output", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data["today"]) == 2
    assert data["today"][0] == {"time": "9:30am", "label": "Piano", "who": "kid1"}
    assert len(data["tomorrow"]) == 1
    assert len(data["missions"]) == 1
    assert data["missions"][0]["who"] == "Laila"
    assert data["next_event"]["label"] == "Far future trip"
    assert data["next_event"]["days_until"] > 0
    assert data["watching_next"]["label"] == "Dune 2021"


def test_brief_handles_missing_files(tmp_path: Path):
    """If a manifest names a file that doesn't exist, brief still renders empty sections."""
    feed = _write_manifest(
        tmp_path,
        {
            "calendar": tmp_path / "missing-calendar.md",
            "missions": tmp_path / "missing-missions.md",
            "events": tmp_path / "missing-events.md",
            "activities": tmp_path / "missing-activities.md",
        },
    )
    result = runner.invoke(app, ["brief", "--feed", str(feed)])
    assert result.exit_code == 0, result.output
    assert "TODAY (0)" in result.output
    assert "(nothing scheduled)" in result.output


def test_brief_only_includes_referenced_providers(tmp_path: Path):
    """A manifest with only calendar shouldn't try to print missions/events/queue."""
    cal = tmp_path / "calendar.md"
    cal.write_text("## Today\n- 9:00am Test\n")
    feed = _write_manifest(tmp_path, {"calendar": cal})
    result = runner.invoke(app, ["brief", "--feed", str(feed), "--output", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data["today"]) == 1
    assert data["missions"] == []
    assert data["next_event"] is None
    assert data["watching_next"] is None
