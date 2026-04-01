from reterminal.cli.commands import find_unsupported_legacy_pages, next_assigned_slot


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
