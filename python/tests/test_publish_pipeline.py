from pathlib import Path

from PIL import Image

from reterminal.app import DisplayPublisher
from reterminal.render import MonoRenderer
from reterminal.scenes import Metric, SceneSpec
from reterminal.scheduler import PriorityScheduler


class StubProvider:
    name = "stub"

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


class RecordingRenderer:
    def __init__(self):
        self.calls = []

    def render(self, scene, *, slot=None, total_slots=None):
        self.calls.append((scene.id, slot, total_slots))
        return Image.new("1", (800, 480), color=1)


class StubDevice:
    def __init__(self):
        self.pushed = []
        self.shown = []
        self.prepare_calls = 0

    def discover_capabilities(self, refresh=False):
        class Capabilities:
            host = "192.168.7.76"
            page_slots = 4
            current_page = 1

        return Capabilities()

    def prepare_push_cycle(self):
        self.prepare_calls += 1
        return self.discover_capabilities()

    def push_pil(self, image, slot):
        self.pushed.append((slot, image.size, image.mode))
        return {"success": True, "page": slot}

    def show_slot(self, slot):
        self.shown.append(slot)
        return {"page": slot}


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
    assert result.shown_slot == 0
    assert result.push_results == {0: {"success": True, "page": 0}}
    assert device.prepare_calls == 1
    assert device.pushed == [(0, (800, 480), "1")]
    assert device.shown == [0]
    assert (preview_dir / "slot-0-hero.png").exists()



def test_publisher_can_activate_an_explicit_slot(tmp_path: Path):
    device = StubDevice()
    publisher = DisplayPublisher(
        providers=[StubProvider()],
        renderer=MonoRenderer(),
        scheduler=PriorityScheduler(),
        device=device,
    )

    result = publisher.publish(preview_dir=tmp_path / "previews", push=True, show_slot=3)

    assert result.shown_slot == 3
    assert device.shown == [3]


def test_publisher_passes_slot_context_to_renderer(tmp_path: Path):
    device = StubDevice()
    renderer = RecordingRenderer()
    publisher = DisplayPublisher(
        providers=[StubProvider()],
        renderer=renderer,
        scheduler=PriorityScheduler(),
        device=device,
    )

    publisher.publish(preview_dir=tmp_path / "previews", push=False)

    assert renderer.calls == [("hero", 0, 4)]
