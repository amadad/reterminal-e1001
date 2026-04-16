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
    page_name: str


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
    page_name: str
    ssid: str
    rssi: int
    uptime_ms: int
    firmware_version: str
    hostname: str
    build_time: str
    build_sha: str
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
