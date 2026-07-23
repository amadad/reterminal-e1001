"""Thin device adapter around the current HTTP firmware contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from PIL import Image
import requests

from reterminal.client import ReTerminal
from reterminal.config import HEIGHT, IMAGE_BYTES, SLOT_COUNT, WIDTH
from reterminal.device.capabilities import DeviceCapabilities
from reterminal.encoding import pil_to_raw
from reterminal.exceptions import PageError
from reterminal.payloads import JSONObject, PushResultPayload


@dataclass(slots=True)
class SlotSnapshot:
    """Exact raw bitmap read back from a stored device slot."""

    host: str
    page: int
    width: int
    height: int
    image_bytes: int
    sha256: str
    page_name: str | None = None
    raw: bytes = field(default=b"", repr=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "page": self.page,
            "page_name": self.page_name,
            "width": self.width,
            "height": self.height,
            "image_bytes": self.image_bytes,
            "sha256": self.sha256,
        }


class ReTerminalDevice:
    """Safe host-side interface to the current 4-slot firmware."""

    def __init__(self, host: str | None = None, *, client: ReTerminal | None = None):
        self.client = client or ReTerminal(host)
        self._capabilities: DeviceCapabilities | None = None
        self._last_seen_uptime_ms: int | None = None
        self._slot_hashes: dict[int, str] = {}

    def discover_capabilities(self, refresh: bool = False) -> DeviceCapabilities:
        if self._capabilities is not None and not refresh:
            return self._capabilities

        status = self.client.status()
        uptime_ms = status.get("uptime_ms")
        page_slots = int(status.get("page_slots", SLOT_COUNT))
        current_page = status.get("current_page")
        self._capabilities = DeviceCapabilities(
            host=self.client.host,
            width=WIDTH,
            height=HEIGHT,
            image_bytes=IMAGE_BYTES,
            page_slots=page_slots,
            current_page=current_page,
            current_page_name=(
                f"slot-{current_page}" if isinstance(current_page, int) else None
            ),
            ssid=status.get("ssid"),
            rssi=status.get("rssi"),
            uptime_ms=uptime_ms,
            firmware_version=status.get("firmware_version"),
            hostname=status.get("hostname"),
            build_time=status.get("build_time"),
            build_sha=status.get("build_sha"),
            reset_reason=status.get("reset_reason"),
            free_heap=status.get("free_heap"),
            free_psram=status.get("free_psram"),
            battery_mv=status.get("battery_mv"),
            boot_count=status.get("boot_count"),
            wake_interval_s=status.get("wake_interval_s"),
            diagnostic_timeout_ms=status.get("diagnostic_timeout_ms"),
            littlefs_used_bytes=status.get("littlefs_used_bytes"),
            event_log_total=status.get("event_log_total"),
            snapshot_readback=True,
            loaded_pages=[bool(value) for value in status.get("loaded_pages", [])],
            slot_names=[f"slot-{slot}" for slot in range(page_slots)],
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

    def push_pil(self, image: Image.Image, slot: int, *, force: bool = False) -> PushResultPayload:
        self.ensure_valid_slot(slot)
        raw = pil_to_raw(image)
        digest = hashlib.sha256(raw).hexdigest()
        if not force and self._slot_hashes.get(slot) == digest:
            return {"skipped": True, "page": slot}

        result = self.client.push_raw(raw, page=slot)
        self._slot_hashes[slot] = digest
        return result

    def snapshot(self, slot: int | None = None) -> SlotSnapshot:
        caps = self.discover_capabilities(refresh=True)
        target_slot = slot if slot is not None else caps.current_page
        if target_slot is None:
            raise PageError("No current slot available to snapshot")
        self.ensure_valid_slot(target_slot)

        try:
            raw = self.client.snapshot_raw(page=target_slot)
        except requests.HTTPError as exc:
            response = exc.response
            if response is not None and response.status_code in {404, 405, 501}:
                raise RuntimeError("/snapshot unavailable") from exc
            raise

        if len(raw) != caps.image_bytes:
            raise RuntimeError(f"Snapshot expected {caps.image_bytes} bytes, got {len(raw)}")

        page_name = None
        if target_slot == caps.current_page:
            page_name = caps.current_page_name
        elif target_slot < len(caps.slot_names):
            page_name = caps.slot_names[target_slot]

        return SlotSnapshot(
            host=self.client.host,
            page=target_slot,
            page_name=page_name,
            width=caps.width,
            height=caps.height,
            image_bytes=caps.image_bytes,
            sha256=hashlib.sha256(raw).hexdigest(),
            raw=raw,
        )

    def show_slot(self, slot: int) -> JSONObject:
        self.ensure_valid_slot(slot)
        return self.client.set_page(slot)
