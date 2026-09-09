import json
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from reterminal.cli.app import app
from reterminal.family.calendar_export import export_calendar


NOW = datetime(2026, 9, 8, 17, 0, tzinfo=ZoneInfo("America/New_York"))
CALENDARS = {"kind": "calendar#calendarList", "items": [{"id": "family-id", "summary": "Family"}]}


def event(**changes):
    result = {
        "id": "event-id", "summary": "Practice", "status": "tentative", "location": "School",
        "start": {"dateTime": "2026-09-08T15:00:00-04:00"},
        "end": {"dateTime": "2026-09-08T16:00:00-04:00"},
    }
    result.update(changes)
    return result


def mock_gws(monkeypatch, pages):
    calls = []
    pending = iter(pages)

    def run(args, **kwargs):
        calls.append((args, kwargs))
        page = next(pending)
        if isinstance(page, Exception):
            raise page
        return SimpleNamespace(stdout=json.dumps(page))

    monkeypatch.setattr("reterminal.family.calendar_export.subprocess.run", run)
    return calls


def export(tmp_path, **kwargs):
    return export_calendar(tmp_path / "calendar.json", config_dir=Path("/account/config"),
                           now=NOW, **kwargs)


def test_full_day_query_keeps_elapsed_events_and_original_fields(monkeypatch, tmp_path):
    calls = mock_gws(monkeypatch, [CALENDARS, {"kind": "calendar#events", "items": [event()]}])
    result = export(tmp_path)
    params = json.loads(calls[1][0][calls[1][0].index("--params") + 1])
    assert params["timeMin"] == "2026-09-08T00:00:00-04:00"
    assert params["timeMax"] == "2026-09-29T00:00:00-04:00"
    assert params["singleEvents"] is True
    assert params["calendarId"] == "family-id"
    assert calls[1][1]["env"]["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] == "/account/config"
    assert result["events"] == [{"id": "event-id", "summary": "Practice", "status": "tentative",
                                 "start": "2026-09-08T15:00:00-04:00",
                                 "end": "2026-09-08T16:00:00-04:00", "location": "School"}]
    assert result["end_date"] == "2026-09-28"
    assert result["checked_at"] == NOW.isoformat()
    assert json.loads((tmp_path / "calendar.json").read_text()) == result
    assert result["source"]["calendar_id"] == "family-id"


def test_all_day_times_not_inferred_from_title_and_pagination_completes(monkeypatch, tmp_path):
    all_day = event(summary="Meeting 9 AM", start={"date": "2026-09-08"},
                    end={"date": "2026-09-10"}, status="confirmed")
    calls = mock_gws(monkeypatch, [
        CALENDARS,
        {"kind": "calendar#events", "items": [all_day], "nextPageToken": "page-2"},
        {"kind": "calendar#events", "items": [{"id": "cancelled", "status": "cancelled"}]},
    ])
    result = export(tmp_path)
    assert result["events"][0]["start"] == "2026-09-08"
    assert result["events"][0]["end"] == "2026-09-10"
    assert result["events"][0]["summary"] == "Meeting 9 AM"
    assert len(result["events"]) == 1
    assert json.loads(calls[2][0][5])["pageToken"] == "page-2"


@pytest.mark.parametrize("bad_page", [
    {"error": {"message": "upstream failure"}},
    {},
    {"kind": "calendar#events", "items": "wrong"},
    {"kind": "calendar#events", "items": [event(end={"date": "2026-09-08"})]},
    {"kind": "calendar#events", "items": [event(start={"dateTime": "2026-09-08T15:00:00"})]},
    subprocess.CalledProcessError(1, "gws"),
])
def test_failed_export_preserves_last_good_content_and_mtime(monkeypatch, tmp_path, bad_page):
    destination = tmp_path / "calendar.json"
    destination.write_text("last good")
    mtime = destination.stat().st_mtime_ns
    mock_gws(monkeypatch, [CALENDARS, bad_page])
    with pytest.raises((ValueError, subprocess.SubprocessError)):
        export(tmp_path)
    assert destination.read_text() == "last good"
    assert destination.stat().st_mtime_ns == mtime
    assert list(tmp_path.iterdir()) == [destination]


def test_ambiguous_calendar_cannot_replace_source(monkeypatch, tmp_path):
    mock_gws(monkeypatch, [{"kind": "calendar#calendarList", "items": [
        {"id": "first", "summary": "Family"}, {"id": "second", "summary": "Family"},
    ]}])
    with pytest.raises(ValueError, match="exactly one"):
        export(tmp_path)
    assert not (tmp_path / "calendar.json").exists()


def test_dst_window_uses_local_midnights(monkeypatch, tmp_path):
    calls = mock_gws(monkeypatch, [CALENDARS, {"kind": "calendar#events"}])
    export_calendar(tmp_path / "calendar.json", config_dir=Path("/account/config"), days=2,
                    now=datetime(2026, 10, 31, 20, tzinfo=ZoneInfo("America/New_York")))
    params = json.loads(calls[1][0][5])
    assert params["timeMin"] == "2026-10-31T00:00:00-04:00"
    assert params["timeMax"] == "2026-11-02T00:00:00-05:00"


def test_cli_exports_without_device_mutation_and_failure_is_nonzero(monkeypatch, tmp_path):
    mock_gws(monkeypatch, [CALENDARS, {"kind": "calendar#events"}])
    args = ["calendar-export", "--destination", str(tmp_path / "calendar.json"),
            "--config-dir", "/account/config"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["events"] == 0
    mock_gws(monkeypatch, [subprocess.CalledProcessError(1, "gws", stderr="private detail")])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert "previous source retained" in result.output
    assert "private detail" not in result.output
