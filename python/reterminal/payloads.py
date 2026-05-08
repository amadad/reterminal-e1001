"""Shared payload and JSON-compatible value types."""

from __future__ import annotations

from typing import TypeAlias, TypedDict

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]


class StatusPayload(TypedDict, total=False):
    ip: str
    rssi: int
    ssid: str
    uptime_ms: int
    free_heap: int
    current_page: int
    current_page_name: str


class PageInfoPayload(TypedDict, total=False):
    page: int
    name: str
    total: int
    loaded: bool


class CapabilitiesPayload(TypedDict, total=False):
    width: int
    height: int
    image_bytes: int
    page_slots: int
    current_page: int
    current_page_name: str
    ssid: str
    rssi: int
    uptime_ms: int
    firmware_version: str
    hostname: str
    build_time: str
    build_sha: str
    reset_reason: str
    wifi_connected: bool
    wifi_status: int
    wifi_reconnect_attempts: int
    last_wifi_ok_ms: int
    last_wifi_lost_ms: int
    last_wifi_reconnect_ms: int
    wifi_down_ms: int
    wifi_self_restart_ms: int
    self_restart_count: int
    last_self_restart_reason: str
    last_self_restart_uptime_ms: int
    mdns_ready: bool
    ota_ready: bool
    loop_watchdog_armed: bool
    loop_watchdog_timeout_s: int
    loop_watchdog_init_status: int
    loop_watchdog_add_status: int
    free_psram: int
    min_free_heap: int
    littlefs_total_bytes: int
    littlefs_used_bytes: int
    snapshot_readback: bool
    loaded_pages: list[bool]
    slot_names: list[str]


class PushResultPayload(TypedDict, total=False):
    success: bool
    page: int
    displayed: bool
    skipped: bool


class ClearResultPayload(TypedDict, total=False):
    success: bool
    page: int
    all: bool
