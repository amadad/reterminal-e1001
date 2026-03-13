from pathlib import Path

from reterminal.app import DisplayPublisher
from reterminal.render import MonoRenderer
from reterminal.scenes import Metric, SceneSpec
from reterminal.scheduler import PriorityScheduler


class StubProvider:
    def fetch(self):
        return [
            SceneSpec(
                id="hero",
                kind="hero",
                title="Agents",
                subtitle="Paperclip bridge pending",
                priority=100,
                metric=Metric(label="Active", value="3"),
                body=["orb shipping", "kara researching"],
            )
        ]


class StubDevice:
    def __init__(self):
        self.pushed = []

    def discover_capabilities(self):
        class Capabilities:
            page_slots = 4

        return Capabilities()

    def push_pil(self, image, slot):
        self.pushed.append((slot, image.size, image.mode))


def test_publisher_renders_preview_and_pushes_to_slots(tmp_path: Path):
    preview_dir = tmp_path / "previews"
    device = StubDevice()
    publisher = DisplayPublisher(
        providers=[StubProvider()],
        renderer=MonoRenderer(),
        scheduler=PriorityScheduler(),
        device=device,
    )

    result = publisher.publish(preview_dir=preview_dir, push=True)

    assert result.slot_count == 4
    assert result.assignments[0].scene.id == "hero"
    assert device.pushed == [(0, (800, 480), "1")]
    assert (preview_dir / "slot-0-hero.png").exists()
