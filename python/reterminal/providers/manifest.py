"""Provider-manifest feed format.

The legacy feed shape was a precomputed list of scenes:

    {"scenes": [{"id": ..., "kind": ..., "preferred_slot": 0, ...}, ...]}

That worked when an upstream pipeline rendered scenes and dropped them in a
JSON file. For the live kitchen display we want the inverse: the feed names
*providers and their inputs*, and each provider parses its source on every
fetch. Editing the markdown is the only trigger the host pipeline needs.

A manifest file looks like:

    {
      "providers": [
        {"type": "calendar",   "calendar_id": "family@group.calendar.google.com"},
        {"type": "missions",   "path": "~/madad/family/missions.md"},
        {"type": "events",     "path": "~/madad/family/events.md"},
        {"type": "activities", "path": "~/madad/family/activities.md"}
      ]
    }

Providers register themselves into PROVIDER_REGISTRY; load_manifest +
build_providers turn a manifest file into a list[SceneProvider] the existing
DisplayPublisher can consume unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reterminal.providers.base import SceneProvider


ProviderFactory = Callable[[Mapping[str, Any]], SceneProvider]

PROVIDER_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(type_name: str, factory: ProviderFactory) -> None:
    """Register a provider factory under a manifest type string."""
    PROVIDER_REGISTRY[type_name] = factory


@dataclass(slots=True)
class ProviderEntry:
    type: str
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProviderEntry:
        if "type" not in data:
            raise ValueError("Provider entry missing required 'type' field")
        type_name = data["type"]
        if not isinstance(type_name, str) or not type_name:
            raise ValueError("Provider 'type' must be a non-empty string")
        config = {k: v for k, v in data.items() if k != "type"}
        return cls(type=type_name, config=config)


@dataclass(slots=True)
class FeedManifest:
    providers: list[ProviderEntry]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FeedManifest:
        if "providers" not in data:
            raise ValueError("Manifest missing required 'providers' list")
        raw = data["providers"]
        if not isinstance(raw, list):
            raise ValueError("Manifest 'providers' must be a list")
        return cls(providers=[ProviderEntry.from_dict(item) for item in raw])


def is_manifest_shape(data: Any) -> bool:
    """Return True if `data` looks like a provider manifest (vs scene list)."""
    return isinstance(data, Mapping) and "providers" in data


def load_manifest(path: Path | str) -> FeedManifest:
    """Read a manifest JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Manifest not found: {p}")
    return FeedManifest.from_dict(json.loads(p.read_text()))


def build_providers(manifest: FeedManifest) -> list[SceneProvider]:
    """Resolve manifest entries to SceneProvider instances via the registry.

    Raises KeyError for any type string that has no registered factory — that
    is intentional: a typo in the manifest should fail loudly, not silently
    drop a slot.
    """
    providers: list[SceneProvider] = []
    for entry in manifest.providers:
        factory = PROVIDER_REGISTRY.get(entry.type)
        if factory is None:
            raise KeyError(
                f"Unknown provider type {entry.type!r}. "
                f"Registered types: {sorted(PROVIDER_REGISTRY)}"
            )
        providers.append(factory(entry.config))
    return providers
