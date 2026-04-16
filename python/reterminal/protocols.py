"""Shared structural interfaces for publish pipeline components."""

from __future__ import annotations

from typing import Protocol

from PIL import Image

from reterminal.payloads import JSONObject, PushResultPayload
from reterminal.scenes import SceneSpec


class DeviceCapabilitiesLike(Protocol):
    """Minimum capability surface the publisher needs."""

    host: str
    page_slots: int


class SceneRenderer(Protocol):
    """Renderer that can turn a scene into a PIL image."""

    def render(
        self,
        scene: SceneSpec,
        *,
        slot: int | None = None,
        total_slots: int | None = None,
    ) -> Image.Image:
        """Render one scene for a specific slot context."""


class DisplayDevice(Protocol):
    """Device adapter used by the publish pipeline."""

    def discover_capabilities(self, refresh: bool = False) -> DeviceCapabilitiesLike:
        """Return the current device contract."""

    def prepare_push_cycle(self) -> DeviceCapabilitiesLike:
        """Refresh any per-cycle state before uploads begin."""

    def push_pil(self, image: Image.Image, slot: int) -> PushResultPayload:
        """Upload an image into a device slot."""

    def show_slot(self, slot: int) -> JSONObject:
        """Make a slot visible on the device."""
