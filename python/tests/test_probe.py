from reterminal.probe import (
    analyze_slot_result,
    infer_contiguous_slot_count,
    missing_status_fields,
)


def test_missing_status_fields_reports_only_missing_items():
    status = {
        "ip": "192.168.7.77",
        "rssi": -40,
        "ssid": "lab",
        "uptime_ms": 1234,
    }

    assert missing_status_fields(status) == ["free_heap", "current_page", "page_name"]


def test_analyze_slot_result_detects_invalid_slot_fallback_behavior():
    result = analyze_slot_result(
        slot=4,
        push_response={"success": True, "displayed": True},
        set_response={"page": 0, "name": "dashboard"},
    )

    assert result.push_stored is False
    assert result.push_displayed is True
    assert result.selected_page_matches is False
    assert "displayed immediately instead of storing" in result.notes
    assert "set_page returned 0" in result.notes


def test_infer_contiguous_slot_count_stops_at_first_failed_slot():
    slot_results = [
        analyze_slot_result(0, {"page": 0}, {"page": 0}),
        analyze_slot_result(1, {"page": 1}, {"page": 1}),
        analyze_slot_result(2, {"success": True, "displayed": True}, {"page": 0}),
        analyze_slot_result(3, {"page": 3}, {"page": 3}),
    ]

    assert infer_contiguous_slot_count(slot_results) == 2
