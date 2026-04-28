import hashlib

from PIL import Image
import pytest

from reterminal.device.adapter import ReTerminalDevice


class FakeClient:
    def __init__(self):
        self.host = "192.168.7.76"
        self.status_payload = {"uptime_ms": 1000, "page_name": "dashboard"}
        self.page_payload = {"total": 4, "page": 0, "name": "dashboard"}
        self.capabilities_payload = {
            "width": 800,
            "height": 480,
            "image_bytes": 48000,
            "page_slots": 4,
            "current_page": 0,
            "current_page_name": "dashboard",
            "uptime_ms": 1000,
            "snapshot_readback": True,
            "loaded_pages": [True, True, True, True],
            "slot_names": ["slot-0", "slot-1", "slot-2", "slot-3"],
        }
        self.snapshot_payload = b"\xff" * 48000
        self.pushes = []
        self.shown = []
        self.clears = []
        self.snapshots = []

    def status(self):
        return dict(self.status_payload)

    def get_page(self):
        return dict(self.page_payload)

    def capabilities(self):
        if self.capabilities_payload is None:
            raise RuntimeError("/capabilities unavailable")
        return dict(self.capabilities_payload)

    def push_raw(self, data, page=None):
        self.pushes.append((page, len(data)))
        return {"success": True, "page": page}

    def snapshot_raw(self, page=None):
        self.snapshots.append(page)
        return self.snapshot_payload

    def set_page(self, page):
        self.shown.append(page)
        return {"page": page, "name": f"slot-{page}"}

    def clear(self, *, page=None, all=False):
        self.clears.append({"page": page, "all": all})
        return {"success": True, "page": page, "all": all}



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
    client.capabilities_payload["uptime_ms"] = 50
    device.prepare_push_cycle()
    result = device.push_pil(image, 0)

    assert result == {"success": True, "page": 0}
    assert client.pushes == [(0, 48000), (0, 48000)]



def test_device_prefers_firmware_capabilities_endpoint_when_available():
    client = FakeClient()
    client.capabilities_payload = {
        "width": 800,
        "height": 480,
        "image_bytes": 48000,
        "page_slots": 4,
        "current_page": 2,
        "current_page_name": "slot-2",
        "ssid": "HORUS",
        "rssi": -55,
        "uptime_ms": 4321,
        "firmware_version": "test-fw",
        "hostname": "reterminal",
        "build_time": "Apr 01 2026 14:30:00",
        "snapshot_readback": True,
        "loaded_pages": [True, False, True, True],
        "slot_names": ["slot-0", "slot-1", "slot-2", "slot-3"],
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
    assert snapshot.page_name == "dashboard"
    assert snapshot.image_bytes == 48000
    assert snapshot.sha256 == hashlib.sha256(client.snapshot_payload).hexdigest()
    assert client.snapshots == [0]



def test_device_clear_invalidates_slot_hashes():
    client = FakeClient()
    device = ReTerminalDevice(client=client)
    image = Image.new("1", (800, 480), color=1)

    device.push_pil(image, 0)
    cleared = device.clear(slot=0)
    reuploaded = device.push_pil(image, 0)

    assert cleared == {"success": True, "page": 0, "all": False}
    assert reuploaded == {"success": True, "page": 0}
    assert client.clears == [{"page": 0, "all": False}]
    assert client.pushes == [(0, 48000), (0, 48000)]



def test_device_does_not_hide_unexpected_capabilities_errors():
    client = FakeClient()

    def broken_capabilities():
        raise RuntimeError("firmware returned invalid capabilities")

    client.capabilities = broken_capabilities

    with pytest.raises(RuntimeError, match="invalid capabilities"):
        ReTerminalDevice(client=client).discover_capabilities(refresh=True)
