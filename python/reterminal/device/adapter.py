"""Thin device adapter around the current HTTP firmware contract."""

from __future__ import annotations

from typing import Optional

from PIL import Image

from reterminal.client import ReTerminal
from reterminal.device.capabilities import DeviceCapabilities
from reterminal.encoding import pil_to_raw
from reterminal.exceptions import PageError


class ReTerminalDevice:
    """Safe host-side interface to the current 4-slot firmware."""

    def __init__(self, host: Optional[str] = None):
        self.client = ReTerminal(host)
        self._capabilities: Optional[DeviceCapabilities] = None

    def discover_capabilities(self, refresh: bool = False) -> DeviceCapabilities:
        if self._capabilities is not None and not refresh:
            return self._capabilities

        status = self.client.status()
        page = self.client.get_page()
        self._capabilities = DeviceCapabilities(
            host=self.client.host,
            page_slots=int(page.get("total", 4)),
            current_page=page.get("page"),
            current_page_name=page.get("name") or status.get("page_name"),
            ssid=status.get("ssid"),
            rssi=status.get("rssi"),
            uptime_ms=status.get("uptime_ms"),
        )
        return self._capabilities

    def ensure_valid_slot(self, slot: int) -> None:
        caps = self.discover_capabilities()
        if slot < 0 or slot >= caps.page_slots:
            raise PageError(f"Slot must be between 0 and {caps.page_slots - 1}, got {slot}")

    def push_pil(self, image: Image.Image, slot: int) -> dict:
        self.ensure_valid_slot(slot)
        raw = pil_to_raw(image)
        return self.client.push_raw(raw, page=slot)

    def show_slot(self, slot: int) -> dict:
        self.ensure_valid_slot(slot)
        return self.client.set_page(slot)
