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



def test_clear_command_invokes_device_clear(monkeypatch):
    captured = {}

    class StubDevice:
        def __init__(self, host=None):
            captured["host"] = host

        def clear(self, slot=None, all=False):
            captured["slot"] = slot
            captured["all"] = all
            return {"success": True, "page": slot, "all": all}

    monkeypatch.setattr("reterminal.cli.commands.ReTerminalDevice", StubDevice)

    result = runner.invoke(app, ["clear", "--host", "192.168.7.97", "--page", "2"])

    assert result.exit_code == 0
    assert '"page": 2' in result.stdout
    assert captured == {"host": "192.168.7.97", "slot": 2, "all": False}
