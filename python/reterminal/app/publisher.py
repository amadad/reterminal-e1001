"""Publishing pipeline from scene providers to previews/device slots."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
import re

from reterminal.payloads import PushResultPayload
from reterminal.protocols import DisplayDevice, SceneRenderer
from reterminal.providers import SceneProvider
from reterminal.render import MonoRenderer
from reterminal.scheduler import PriorityScheduler, SlotAssignment
from reterminal.scenes import SceneSpec


@dataclass(slots=True)
class PublishResult:
    """Result of a publish run."""

    slot_count: int
    scenes: list[SceneSpec]
    assignments: dict[int, SlotAssignment]
    preview_paths: list[Path] = field(default_factory=list)
    push_results: dict[int, PushResultPayload] = field(default_factory=dict)
    shown_slot: int | None = None


class DisplayPublisher:
    """Collect scenes, schedule them, render them, then preview or push."""

    def __init__(
        self,
        *,
        providers: Sequence[SceneProvider],
        renderer: SceneRenderer | None = None,
        scheduler: PriorityScheduler | None = None,
        device: DisplayDevice | None = None,
    ):
        self.providers = list(providers)
        self.renderer = renderer or MonoRenderer()
        self.scheduler = scheduler or PriorityScheduler()
        self.device = device

    def publish(
        self,
        *,
        preview_dir: Path | None = None,
        push: bool = False,
        slot_count: int | None = None,
        show_slot: int | None = None,
    ) -> PublishResult:
        scenes = self._collect_scenes()
        if push and self.device is not None:
            self.device.prepare_push_cycle()
        resolved_slot_count = slot_count or self._resolve_slot_count()
        assignments = self.scheduler.assign(scenes, resolved_slot_count)

        preview_paths: list[Path] = []
        push_results: dict[int, PushResultPayload] = {}
        if preview_dir:
            preview_dir.mkdir(parents=True, exist_ok=True)

        for slot, assignment in sorted(assignments.items()):
            image = self.renderer.render(
                assignment.scene,
                slot=slot,
                total_slots=resolved_slot_count,
            )
            if preview_dir:
                path = preview_dir / f"slot-{slot}-{self._slugify(assignment.scene.id)}.png"
                image.save(path)
                preview_paths.append(path)
            if push:
                if self.device is None:
                    raise ValueError("A device adapter is required when push=True")
                push_results[slot] = self.device.push_pil(image, slot)

        shown_slot: int | None = None
        if push and show_slot is not None:
            if self.device is None:
                raise ValueError("A device adapter is required when push=True")
            shown_slot = self._resolve_show_slot(assignments, show_slot)
            self.device.show_slot(shown_slot)

        return PublishResult(
            slot_count=resolved_slot_count,
            scenes=scenes,
            assignments=assignments,
            preview_paths=preview_paths,
            push_results=push_results,
            shown_slot=shown_slot,
        )

    def _collect_scenes(self) -> list[SceneSpec]:
        deduped: dict[str, SceneSpec] = {}
        for provider in self.providers:
            for scene in provider.fetch():
                existing = deduped.get(scene.id)
                if existing is None or scene.priority >= existing.priority:
                    deduped[scene.id] = scene
        return sorted(deduped.values(), key=lambda scene: scene.sort_key())

    def _resolve_slot_count(self) -> int:
        if self.device is not None:
            return self.device.discover_capabilities().page_slots
        return 4

    @staticmethod
    def _resolve_show_slot(
        assignments: dict[int, SlotAssignment],
        requested_slot: int | None,
    ) -> int:
        if requested_slot is not None:
            return requested_slot
        if 0 in assignments:
            return 0
        return min(assignments)

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
        return slug or "scene"
