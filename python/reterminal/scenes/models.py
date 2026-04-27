"""Scene models for the host-rendered display pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from reterminal.payloads import JSONObject, JSONValue

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


@dataclass(slots=True)
class Metric:
    """Single metric/value pair for dashboard-style scenes."""

    label: str
    value: str
    detail: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "Metric":
        return cls(
            label=str(data["label"]),
            value=str(data["value"]),
            detail=_optional_str(data.get("detail")),
        )


@dataclass(slots=True)
class SceneSpec:
    """Structured scene description independent of rendering or device slots."""

    id: str
    kind: str
    title: str
    subtitle: str | None = None
    priority: int = 0
    preferred_slot: int | None = None
    metric: Metric | None = None
    metrics: list[Metric] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    footer: str | None = None
    image_path: str | None = None
    image_url: str | None = None
    meta: JSONObject = field(default_factory=dict)
    # When set, MonoRenderer skips its own kind-dispatch and returns this
    # bitmap as-is. Lets providers that own their layout (missions, events,
    # activities, calendar) render directly without inventing new SceneRenderer
    # kinds for each. PIL.Image.Image at runtime; typed loosely so models.py
    # does not need to import PIL.
    prerendered: "PILImage | None" = None

    @classmethod
    def from_dict(cls, data: Mapping[str, object], *, base_dir: Path | None = None) -> "SceneSpec":
        metric_data = data.get("metric")
        metrics_data = data.get("metrics")
        image_path = _optional_str(data.get("image_path"))
        if image_path and base_dir is not None:
            image_path = str((base_dir / image_path).resolve())

        preferred_slot = data.get("preferred_slot")
        return cls(
            id=str(data["id"]),
            kind=str(data.get("kind", "hero")),
            title=str(data["title"]),
            subtitle=_optional_str(data.get("subtitle")),
            priority=_coerce_int(data.get("priority"), default=0),
            preferred_slot=preferred_slot if isinstance(preferred_slot, int) else None,
            metric=Metric.from_dict(metric_data) if isinstance(metric_data, Mapping) else None,
            metrics=[Metric.from_dict(item) for item in _mapping_list(metrics_data)],
            body=_string_list(data.get("body")),
            items=_string_list(data.get("items")),
            footer=_optional_str(data.get("footer")),
            image_path=image_path,
            image_url=_optional_str(data.get("image_url")),
            meta=_json_object(data.get("meta")),
        )

    def sort_key(self) -> tuple[int, int, str]:
        """Sort key for scheduler priority ordering."""
        pinned_bonus = 1 if self.preferred_slot is not None else 0
        return (-self.priority, -pinned_bonus, self.id)


def _coerce_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _json_object(value: object) -> JSONObject:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return str(value)
