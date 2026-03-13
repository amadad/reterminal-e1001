from reterminal.scheduler import PriorityScheduler
from reterminal.scenes import Metric, SceneSpec


def test_scheduler_respects_preferred_slots_before_filling_remaining_slots():
    scenes = [
        SceneSpec(
            id="pinned-hero",
            kind="hero",
            title="Pinned",
            priority=50,
            preferred_slot=2,
            body=["critical"],
        ),
        SceneSpec(
            id="high-priority-feed",
            kind="bulletin",
            title="Feed",
            priority=40,
            items=["item one"],
        ),
        SceneSpec(
            id="metrics",
            kind="metrics",
            title="Metrics",
            priority=30,
            metrics=[Metric(label="Runs", value="12")],
        ),
    ]

    assignments = PriorityScheduler().assign(scenes, slot_count=4)

    assert assignments[2].scene.id == "pinned-hero"
    assert assignments[0].scene.id == "high-priority-feed"
    assert assignments[1].scene.id == "metrics"


def test_scheduler_resolves_slot_conflicts_by_priority():
    scenes = [
        SceneSpec(id="low", kind="hero", title="Low", priority=10, preferred_slot=1),
        SceneSpec(id="high", kind="hero", title="High", priority=20, preferred_slot=1),
    ]

    assignments = PriorityScheduler().assign(scenes, slot_count=2)

    assert assignments[1].scene.id == "high"
    assert assignments[0].scene.id == "low"
