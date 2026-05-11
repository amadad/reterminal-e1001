"""Provider-manifest feed format.

A manifest names providers and their inputs so each provider re-parses its
source on every fetch. This is the inverse of the older scene-list format
({"scenes": [...]}) where an upstream pipeline pre-rendered scenes into JSON.

    {
      "providers": [
        {"type": "calendar",   "path": "~/reterminal-content/family/calendar.md",   "slot": 0},
        {"type": "missions",   "path": "~/reterminal-content/family/missions.md",   "slot": 1},
        {"type": "events",     "path": "~/reterminal-content/family/events.md",     "slot": 2},
        {"type": "activities", "path": "~/reterminal-content/family/activities.md", "slot": 3}
      ]
    }

Providers register themselves into PROVIDER_REGISTRY; load_manifest +
build_providers turn a manifest file into a list[SceneProvider] the existing
DisplayPublisher can consume unchanged. Manifest-level `slot` pins are applied
outside the provider so source adapters do not need physical-slot knowledge.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from reterminal.payloads import JSONValue
from reterminal.providers.base import SceneProvider
from reterminal.scenes import SceneSpec


ProviderFactory = Callable[[Mapping[str, JSONValue]], SceneProvider]

PROVIDER_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(type_name: str, factory: ProviderFactory) -> None:
    """Register a provider factory under a manifest type string."""
    PROVIDER_REGISTRY[type_name] = factory


@dataclass(slots=True)
class ProviderEntry:
    type: str
    config: dict[str, JSONValue] = field(default_factory=dict)
    slot: int | None = None

    def path(self) -> Path | None:
        """Return the entry's `path` config as an expanded Path, or None.

        Most provider configs name a markdown source via `path`; non-display
        consumers (lint, brief, FSEvents watch loop) all want the expanded
        absolute form. Returning None for missing-or-non-string keeps callers
        from having to repeat the `isinstance(raw, str)` guard.
        """
        raw = self.config.get("path")
        if isinstance(raw, str):
            return Path(raw).expanduser()
        return None

    @classmethod
    def from_dict(cls, data: Mapping[str, JSONValue]) -> ProviderEntry:
        if "type" not in data:
            raise ValueError("Provider entry missing required 'type' field")
        type_name = data["type"]
        if not isinstance(type_name, str) or not type_name:
            raise ValueError("Provider 'type' must be a non-empty string")

        raw_slot = data.get("slot")
        if raw_slot is not None:
            if not isinstance(raw_slot, int) or isinstance(raw_slot, bool) or raw_slot < 0:
                raise ValueError("Provider 'slot' must be a non-negative integer")
            slot = raw_slot
        else:
            slot = None

        config = {k: v for k, v in data.items() if k not in {"type", "slot"}}
        return cls(type=type_name, config=config, slot=slot)


@dataclass(slots=True)
class FeedManifest:
    providers: list[ProviderEntry]

    @classmethod
    def from_dict(cls, data: Mapping[str, JSONValue]) -> FeedManifest:
        if "providers" not in data:
            raise ValueError("Manifest missing required 'providers' list")
        raw = data["providers"]
        if not isinstance(raw, list):
            raise ValueError("Manifest 'providers' must be a list")
        return cls(providers=[ProviderEntry.from_dict(item) for item in raw])


def is_manifest_shape(data: object) -> bool:
    """Return True if `data` looks like a provider manifest (vs scene list)."""
    return isinstance(data, Mapping) and "providers" in data


def load_manifest(path: Path | str) -> FeedManifest:
    """Read a manifest JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Manifest not found: {p}")
    return FeedManifest.from_dict(json.loads(p.read_text()))


@dataclass(slots=True)
class SlottedProvider:
    """Provider wrapper that pins every returned scene to a manifest slot."""

    provider: SceneProvider
    slot: int

    @property
    def name(self) -> str:
        return self.provider.name

    def fetch(self) -> list[SceneSpec]:
        return [replace(scene, preferred_slot=self.slot) for scene in self.provider.fetch()]


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
        provider = factory(entry.config)
        if entry.slot is not None:
            provider = SlottedProvider(provider=provider, slot=entry.slot)
        providers.append(provider)
    return providers
