"""Device capability models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from reterminal.config import HEIGHT, IMAGE_BYTES, WIDTH


@dataclass(slots=True)
class DeviceCapabilities:
    """Host-side view of the current device contract."""

    host: str
    width: int = WIDTH
    height: int = HEIGHT
    image_bytes: int = IMAGE_BYTES
    page_slots: int = 4
    current_page: int | None = None
    current_page_name: str | None = None
    ssid: str | None = None
    rssi: int | None = None
    uptime_ms: int | None = None
    firmware_version: str | None = None
    hostname: str | None = None
    build_time: str | None = None
    build_sha: str | None = None
    snapshot_readback: bool | None = None
    loaded_pages: list[bool] = field(default_factory=list)
    slot_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
