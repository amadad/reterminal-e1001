"""Thin device adapter around the current HTTP firmware contract."""

from __future__ import annotations

import hashlib
from typing import Optional

from PIL import Image

from reterminal.client import ReTerminal
from reterminal.device.capabilities import DeviceCapabilities
from reterminal.encoding import pil_to_raw
from reterminal.exceptions import PageError


class ReTerminalDevice:
    """Safe host-side interface to the current 4-slot firmware."""

    def __init__(self, host: Optional[str] = None, *, client: Optional[ReTerminal] = None):
        self.client = client or ReTerminal(host)
        self._capabilities: Optional[DeviceCapabilities] = None
        self._last_seen_uptime_ms: Optional[int] = None
        self._slot_hashes: dict[int, str] = {}

    def discover_capabilities(self, refresh: bool = False) -> DeviceCapabilities:
        if self._capabilities is not None and not refresh:
            return self._capabilities

        status = self.client.status()
        page = self.client.get_page()
        uptime_ms = status.get("uptime_ms")
        self._capabilities = DeviceCapabilities(
            host=self.client.host,
            page_slots=int(page.get("total", 4)),
            current_page=page.get("page"),
            current_page_name=page.get("name") or status.get("page_name"),
            ssid=status.get("ssid"),
            rssi=status.get("rssi"),
            uptime_ms=uptime_ms,
        )
        if (
            isinstance(self._last_seen_uptime_ms, int)
            and isinstance(uptime_ms, int)
            and uptime_ms < self._last_seen_uptime_ms
        ):
            self._slot_hashes.clear()
        if isinstance(uptime_ms, int):
            self._last_seen_uptime_ms = uptime_ms
        return self._capabilities

    def ensure_valid_slot(self, slot: int) -> None:
        caps = self.discover_capabilities()
        if slot < 0 or slot >= caps.page_slots:
            raise PageError(f"Slot must be between 0 and {caps.page_slots - 1}, got {slot}")

    def prepare_push_cycle(self) -> DeviceCapabilities:
        """Refresh capabilities and clear upload cache after device reboots."""
        return self.discover_capabilities(refresh=True)

    def push_pil(self, image: Image.Image, slot: int, *, force: bool = False) -> dict:
        self.ensure_valid_slot(slot)
        raw = pil_to_raw(image)
        digest = hashlib.sha256(raw).hexdigest()
        if not force and self._slot_hashes.get(slot) == digest:
            return {"skipped": True, "page": slot}

        result = self.client.push_raw(raw, page=slot)
        self._slot_hashes[slot] = digest
        return result

    def show_slot(self, slot: int) -> dict:
        self.ensure_valid_slot(slot)
        return self.client.set_page(slot)
