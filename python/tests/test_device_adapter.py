from PIL import Image

from reterminal.device.adapter import ReTerminalDevice


class FakeClient:
    def __init__(self):
        self.host = "192.168.7.76"
        self.status_payload = {"uptime_ms": 1000, "page_name": "dashboard"}
        self.page_payload = {"total": 4, "page": 0, "name": "dashboard"}
        self.pushes = []
        self.shown = []

    def status(self):
        return dict(self.status_payload)

    def get_page(self):
        return dict(self.page_payload)

    def push_raw(self, data, page=None):
        self.pushes.append((page, len(data)))
        return {"success": True, "page": page}

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
