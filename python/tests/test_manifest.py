import json
from pathlib import Path

import pytest

from reterminal.providers.manifest import (
    PROVIDER_REGISTRY,
    FeedManifest,
    ProviderEntry,
    build_providers,
    is_manifest_shape,
    load_manifest,
    register_provider,
)
from reterminal.scenes import SceneSpec


class _StubProvider:
    name = "stub"

    def __init__(self, config):
        self.config = config

    def fetch(self):
        return [SceneSpec(id="stub", kind="hero", title="stub")]


@pytest.fixture(autouse=True)
def _isolate_registry():
    snapshot = dict(PROVIDER_REGISTRY)
    PROVIDER_REGISTRY.clear()
    yield
    PROVIDER_REGISTRY.clear()
    PROVIDER_REGISTRY.update(snapshot)


def test_provider_entry_requires_type():
    with pytest.raises(ValueError, match="missing required 'type'"):
        ProviderEntry.from_dict({"path": "/x"})


def test_manifest_round_trip(tmp_path: Path):
    path = tmp_path / "kitchen.json"
    path.write_text(
        json.dumps(
            {
                "providers": [
                    {"type": "missions", "path": "~/madad/family/missions.md"},
                    {"type": "calendar", "calendar_id": "cal@example.com"},
                ]
            }
        )
    )
    manifest = load_manifest(path)
    assert [p.type for p in manifest.providers] == ["missions", "calendar"]
    assert manifest.providers[0].config == {"path": "~/madad/family/missions.md"}
    assert manifest.providers[1].config == {"calendar_id": "cal@example.com"}


def test_build_providers_uses_registry():
    register_provider("missions", _StubProvider)
    manifest = FeedManifest(providers=[ProviderEntry(type="missions", config={"path": "/x"})])
    providers = build_providers(manifest)
    assert len(providers) == 1
    assert providers[0].config == {"path": "/x"}


def test_unknown_provider_type_fails_loudly():
    manifest = FeedManifest(providers=[ProviderEntry(type="missions", config={})])
    with pytest.raises(KeyError, match="Unknown provider type 'missions'"):
        build_providers(manifest)


def test_is_manifest_shape_distinguishes_feed_formats():
    assert is_manifest_shape({"providers": []}) is True
    assert is_manifest_shape({"scenes": []}) is False
    assert is_manifest_shape([]) is False


def test_example_kitchen_display_manifest_parses():
    repo_example = Path(__file__).resolve().parent.parent / "examples" / "kitchen-display.json"
    manifest = load_manifest(repo_example)
    types = [p.type for p in manifest.providers]
    assert types == ["calendar", "missions", "events", "activities"]
