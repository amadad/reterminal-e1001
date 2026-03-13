import json

from reterminal.providers.paperclip import PaperclipSceneProvider


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_paperclip_provider_loads_scene_feed(monkeypatch):
    def fake_urlopen(request, timeout=10):
        assert request.full_url == "https://paperclip.local/display-feed"
        assert request.headers["Authorization"] == "Bearer token-123"
        return FakeResponse(
            {
                "scenes": [
                    {
                        "id": "paperclip-job",
                        "kind": "hero",
                        "title": "orb shipping",
                        "priority": 88,
                    }
                ]
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = PaperclipSceneProvider("https://paperclip.local/display-feed", token="token-123")
    scenes = provider.fetch()

    assert scenes[0].id == "paperclip-job"
    assert scenes[0].priority == 88
