"""Device capability models."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from reterminal.config import HEIGHT, IMAGE_BYTES, WIDTH


@dataclass(slots=True)
class DeviceCapabilities:
    """Host-side view of the current device contract."""

    host: str
    width: int = WIDTH
    height: int = HEIGHT
    image_bytes: int = IMAGE_BYTES
    page_slots: int = 4
    current_page: Optional[int] = None
    current_page_name: Optional[str] = None
    ssid: Optional[str] = None
    rssi: Optional[int] = None
    uptime_ms: Optional[int] = None
    firmware_version: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
