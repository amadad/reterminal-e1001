import hashlib

from PIL import Image
import pytest

from reterminal.device.adapter import ReTerminalDevice


class FakeClient:
    def __init__(self):
        self.host = "192.0.2.76"
        self.page_payload = {"total": 4, "page": 0, "name": "dashboard"}
        self.status_payload = {
            "page_slots": 4,
            "current_page": 0,
            "uptime_ms": 1000,
            "loaded_pages": [True, True, True, True],
        }
        self.snapshot_payload = b"\xff" * 48000
        self.pushes = []
        self.shown = []
        self.snapshots = []

    def get_page(self):
        return dict(self.page_payload)

    def status(self):
        return dict(self.status_payload)

    def push_raw(self, data, page=None):
        self.pushes.append((page, len(data)))
        return {"success": True, "page": page}

    def snapshot_raw(self, page=None):
        self.snapshots.append(page)
        return self.snapshot_payload

    def set_page(self, page):
        self.shown.append(page)
        return {"page": page, "name": f"slot-{page}"}



def test_device_skips_unchanged_uploads_within_same_uptime():
    client = FakeClient()
    device = ReTerminalDevice(client=client)
    image = Image.new("1", (800, 480), color=1)

    first = device.push_pil(image, 0)
    second = device.push_pil(image, 0)

    assert first == {"success": True, "page": 0}
    assert second == {"skipped": True, "page": 0}
    assert client.pushes == [(0, 48000)]



def test_device_clears_upload_cache_when_uptime_resets():
    client = FakeClient()
    device = ReTerminalDevice(client=client)
    image = Image.new("1", (800, 480), color=1)

    device.prepare_push_cycle()
    device.push_pil(image, 0)

    client.status_payload["uptime_ms"] = 50
    device.prepare_push_cycle()
    result = device.push_pil(image, 0)

    assert result == {"success": True, "page": 0}
    assert client.pushes == [(0, 48000), (0, 48000)]



def test_device_derives_capabilities_from_status():
    client = FakeClient()
    client.status_payload = {
        "page_slots": 4,
        "current_page": 2,
        "ssid": "ExampleWiFi",
        "rssi": -55,
        "uptime_ms": 4321,
        "firmware_version": "test-fw",
        "hostname": "reterminal",
        "build_time": "Apr 01 2026 14:30:00",
        "free_psram": 8_000_000,
        "littlefs_used_bytes": 192_000,
        "loaded_pages": [True, False, True, True],
    }

    caps = ReTerminalDevice(client=client).discover_capabilities(refresh=True)

    assert caps.width == 800
    assert caps.height == 480
    assert caps.image_bytes == 48000
    assert caps.page_slots == 4
    assert caps.current_page == 2
    assert caps.current_page_name == "slot-2"
    assert caps.hostname == "reterminal"
    assert caps.build_time == "Apr 01 2026 14:30:00"
    assert caps.snapshot_readback is True
    assert caps.loaded_pages == [True, False, True, True]
    assert caps.slot_names == ["slot-0", "slot-1", "slot-2", "slot-3"]



def test_device_snapshot_reads_current_slot():
    client = FakeClient()

    snapshot = ReTerminalDevice(client=client).snapshot()

    assert snapshot.page == 0
    assert snapshot.page_name == "slot-0"
    assert snapshot.image_bytes == 48000
    assert snapshot.sha256 == hashlib.sha256(client.snapshot_payload).hexdigest()
    assert client.snapshots == [0]



def test_device_does_not_hide_unexpected_status_errors():
    client = FakeClient()

    def broken_status():
        raise RuntimeError("firmware returned invalid status")

    client.status = broken_status

    with pytest.raises(RuntimeError, match="invalid status"):
        ReTerminalDevice(client=client).discover_capabilities(refresh=True)
