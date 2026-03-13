"""Priority-based scheduler for mapping logical scenes to hardware slots."""

from __future__ import annotations

from dataclasses import dataclass

from reterminal.scenes import SceneSpec


@dataclass(slots=True)
class SlotAssignment:
    """Scene chosen for a specific physical slot."""

    slot: int
    scene: SceneSpec


class PriorityScheduler:
    """Assign scenes to the limited number of physical slots.

    Strategy:
    - preferred_slot claims are resolved first
    - if multiple scenes want the same slot, highest priority wins
    - remaining scenes fill remaining slots in descending priority order
    """

    def assign(self, scenes: list[SceneSpec], slot_count: int) -> dict[int, SlotAssignment]:
        assignments: dict[int, SlotAssignment] = {}
        if slot_count <= 0:
            return assignments

        preferred: dict[int, list[SceneSpec]] = {}
        overflow: list[SceneSpec] = []

        for scene in scenes:
            if scene.preferred_slot is not None and 0 <= scene.preferred_slot < slot_count:
                preferred.setdefault(scene.preferred_slot, []).append(scene)
            else:
                overflow.append(scene)

        chosen_ids: set[str] = set()
        for slot, slot_scenes in sorted(preferred.items()):
            ranked = sorted(slot_scenes, key=lambda scene: scene.sort_key())
            winner = ranked[0]
            assignments[slot] = SlotAssignment(slot=slot, scene=winner)
            chosen_ids.add(winner.id)
            overflow.extend(ranked[1:])

        remaining_slots = [slot for slot in range(slot_count) if slot not in assignments]
        candidates = [scene for scene in overflow if scene.id not in chosen_ids]
        candidates.sort(key=lambda scene: scene.sort_key())

        for slot, scene in zip(remaining_slots, candidates):
            assignments[slot] = SlotAssignment(slot=slot, scene=scene)
            chosen_ids.add(scene.id)

        return assignments
