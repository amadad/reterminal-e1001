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
    reset_reason: str | None = None
    wifi_connected: bool | None = None
    wifi_status: int | None = None
    wifi_reconnect_attempts: int | None = None
    last_wifi_ok_ms: int | None = None
    last_wifi_lost_ms: int | None = None
    last_wifi_reconnect_ms: int | None = None
    wifi_down_ms: int | None = None
    wifi_self_restart_ms: int | None = None
    self_restart_count: int | None = None
    last_self_restart_reason: str | None = None
    last_self_restart_uptime_ms: int | None = None
    mdns_ready: bool | None = None
    ota_ready: bool | None = None
    loop_watchdog_armed: bool | None = None
    loop_watchdog_timeout_s: int | None = None
    loop_watchdog_init_status: int | None = None
    loop_watchdog_add_status: int | None = None
    free_psram: int | None = None
    min_free_heap: int | None = None
    littlefs_total_bytes: int | None = None
    littlefs_used_bytes: int | None = None
    snapshot_readback: bool | None = None
    loaded_pages: list[bool] = field(default_factory=list)
    slot_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
