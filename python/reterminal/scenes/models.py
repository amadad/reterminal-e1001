"""Scene models for the host-rendered display pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(slots=True)
class Metric:
    """Single metric/value pair for dashboard-style scenes."""

    label: str
    value: str
    detail: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Metric":
        return cls(
            label=str(data["label"]),
            value=str(data["value"]),
            detail=str(data["detail"]) if data.get("detail") is not None else None,
        )


@dataclass(slots=True)
class SceneSpec:
    """Structured scene description independent of rendering or device slots."""

    id: str
    kind: str
    title: str
    subtitle: Optional[str] = None
    priority: int = 0
    preferred_slot: Optional[int] = None
    metric: Optional[Metric] = None
    metrics: list[Metric] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    footer: Optional[str] = None
    image_path: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, base_dir: Optional[Path] = None) -> "SceneSpec":
        metric = Metric.from_dict(data["metric"]) if data.get("metric") else None
        metrics = [Metric.from_dict(item) for item in data.get("metrics", [])]
        image_path = data.get("image_path")
        if image_path and base_dir is not None:
            image_path = str((base_dir / image_path).resolve())

        return cls(
            id=str(data["id"]),
            kind=str(data.get("kind", "hero")),
            title=str(data["title"]),
            subtitle=str(data["subtitle"]) if data.get("subtitle") is not None else None,
            priority=int(data.get("priority", 0)),
            preferred_slot=data.get("preferred_slot"),
            metric=metric,
            metrics=metrics,
            body=[str(item) for item in data.get("body", [])],
            items=[str(item) for item in data.get("items", [])],
            footer=str(data["footer"]) if data.get("footer") is not None else None,
            image_path=image_path,
            meta=dict(data.get("meta", {})),
        )

    def sort_key(self) -> tuple[int, int, str]:
        """Sort key for scheduler priority ordering."""
        pinned_bonus = 1 if self.preferred_slot is not None else 0
        return (-self.priority, -pinned_bonus, self.id)
