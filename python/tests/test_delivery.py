from datetime import datetime, timedelta, timezone
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from reterminal.app.delivery import DeliveryState
from reterminal.app.live import _BitmapCache, _start_content_server


def receipt(**overrides):
    return {"schema_version": 1, "device_id": "test-panel", "outcome": "updated",
            "current_page": 0, "wake_interval_s": 1800, "refresh_returned": True,
            "hashes": {f"slot-{n}": "a" * 64 for n in range(4)},
            "displayed_hash": "a" * 64, **overrides}


def test_receipt_persists_and_proves_storage_separately_from_display(tmp_path):
    path = tmp_path / "receipts.json"
    desired = receipt()["hashes"]
    state = DeliveryState(path)
    assert state.health(desired)["delivery_status"] == "unconfirmed"
    state.request("download", "192.0.2.5", 0)
    assert state.health(desired)["delivery_status"] == "unconfirmed"
    saved = state.record(receipt(displayed_hash=None), "192.0.2.5", desired)
    restored = DeliveryState(path)
    health = restored.health(desired)
    assert health["delivery_status"] == "stored"
    assert health["reported_display_matches"] is False
    assert saved["matches_at_receipt"] is True
    health = restored.health(desired, now=datetime.fromisoformat(saved["received_at"]) + timedelta(seconds=3721))
    assert health["delivery_status"] == "stale"


def test_receipt_pending_failed_and_display_identity():
    state = DeliveryState()
    desired = receipt()["hashes"]
    state.record(receipt(next_poll_in_s=1700), "test")
    assert state.health(desired)["last_receipt"]["next_poll_in_s"] == 1700
    assert state.health(desired)["reported_display_matches"] is True
    assert state.health({**desired, "slot-1": "b" * 64})["delivery_status"] == "pending"
    state.record(receipt(outcome="partial", error="storage failure"), "test")
    assert state.health(desired)["delivery_status"] == "failed"


@pytest.mark.parametrize("change", [
    {"current_page": 4}, {"current_page": True}, {"wake_interval_s": 0},
    {"hashes": {"slot-0": "not-a-hash"}}, {"hashes": {"slot-4": "a" * 64}},
    {"refresh_returned": "yes"}, {"displayed_hash": "bad"},
])
def test_bad_receipt_does_not_replace_last_good(change):
    state = DeliveryState()
    state.record(receipt(), "test")
    with pytest.raises(ValueError):
        state.record(receipt(**change), "test")
    assert len(state.receipts) == 1


def test_content_http_receipt_and_hash_race(tmp_path):
    cache = _BitmapCache()
    cache.mark_current(0, "a" * 64, b"x" * 48000)
    state = DeliveryState(tmp_path / "receipt.json")
    server = _start_content_server(cache, port=0, delivery=state)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/health", timeout=2) as response:
            assert json.load(response)["delivery_status"] == "unconfirmed"
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/content/slot-0?hash=" + "b" * 64, timeout=2)
        assert error.value.code == 409
        request = Request(base + "/receipt", data=json.dumps(receipt()).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=2) as response:
            assert "received_at" in json.load(response)
        with urlopen(base + "/health", timeout=2) as response:
            assert json.load(response)["delivery_status"] == "stored"
        bad = Request(base + "/receipt", data=b"{}")
        with pytest.raises(HTTPError) as error:
            urlopen(bad, timeout=2)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()


def test_corrupt_receipt_file_reports_gap(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text('{"receipts": [{"bad": true}]}')
    state = DeliveryState(path)
    assert state.state_error
    assert state.health(receipt()["hashes"], now=datetime.now(timezone.utc))["delivery_status"] == "unconfirmed"
