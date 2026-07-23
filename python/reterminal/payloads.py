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
    hostname: str
    firmware_version: str
    build_sha: str
    build_time: str
    uptime_ms: int
    free_heap: int
    free_psram: int
    boot_count: int
    wake_interval_s: int
    diagnostic_timeout_ms: int
    battery_mv: int
    page_slots: int
    current_page: int
    reset_reason: int
    littlefs_used_bytes: int
    event_log_total: int
    loaded_pages: list[bool]


class PageInfoPayload(TypedDict, total=False):
    page: int
    name: str
    total: int
    loaded: bool


class PushResultPayload(TypedDict, total=False):
    success: bool
    page: int
    displayed: bool
    skipped: bool
