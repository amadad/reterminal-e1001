import json

from typer.testing import CliRunner

from reterminal.cli.app import app
from reterminal.cli.commands import find_unsupported_legacy_pages, next_assigned_slot


runner = CliRunner()


def test_find_unsupported_legacy_pages_flags_targets_above_device_slot_count():
    unsupported = find_unsupported_legacy_pages(["market", "portfolio", "weather"], page_slots=4)

    assert unsupported == [("portfolio", 4), ("weather", 6)]



def test_next_assigned_slot_rotates_across_assigned_slots():
    assigned_slots = [0, 2, 3]

    assert next_assigned_slot(None, assigned_slots) == 0
    assert next_assigned_slot(0, assigned_slots) == 2
    assert next_assigned_slot(2, assigned_slots) == 3
    assert next_assigned_slot(3, assigned_slots) == 0
    assert next_assigned_slot(9, assigned_slots) == 0



def test_clear_command_rejects_conflicting_target_options():
    result = runner.invoke(app, ["clear", "--all", "--page", "1"])

    assert result.exit_code == 1
    assert "--all cannot be combined with --page" in result.stdout



def test_clear_command_requires_live_flag():
    result = runner.invoke(app, ["clear", "--page", "2"])

    assert result.exit_code == 1
    assert "Use --live to confirm" in result.stdout



def test_clear_command_invokes_device_clear(monkeypatch):
    captured = {}

    class StubClient:
        host = "192.168.7.97"

    class StubDevice:
        def __init__(self, host=None):
            captured["host"] = host
            self.client = StubClient()

        def clear(self, slot=None, all=False):
            captured["slot"] = slot
            captured["all"] = all
            return {"success": True, "page": slot, "all": all}

    monkeypatch.setattr("reterminal.cli.commands.ReTerminalDevice", StubDevice)

    result = runner.invoke(
        app,
        ["clear", "--host", "192.168.7.97", "--page", "2", "--live", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["result"]["page"] == 2
    assert captured == {"host": "192.168.7.97", "slot": 2, "all": False}



def test_push_preview_supports_json_output(tmp_path):
    preview_path = tmp_path / "preview.png"

    result = runner.invoke(
        app,
        ["push", "--text", "hello", "--preview", str(preview_path), "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "preview"
    assert payload["preview_path"] == str(preview_path)
    assert preview_path.exists()



def test_publish_push_requires_live_flag(tmp_path):
    result = runner.invoke(
        app,
        [
            "publish",
            "--feed",
            "examples/agent-feed.json",
            "--preview",
            str(tmp_path / "previews"),
            "--push",
        ],
    )

    assert result.exit_code == 1
    assert "Use --live to confirm" in result.stdout



def test_page_set_requires_live_flag():
    result = runner.invoke(app, ["page", "next"])

    assert result.exit_code == 1
    assert "Use --live to confirm" in result.stdout
