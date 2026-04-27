"""Unit tests for the FSEvents-driven publish loop.

The watchdog-driven loop itself runs forever and is awkward to drive
deterministically in pytest, so these tests cover the two seams that
matter for correctness: bitmap-change detection (no push when nothing
changed) and the per-tick render+push helper.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from reterminal.app.live import _BitmapCache, _publish_once
from reterminal.app.publisher import DisplayPublisher
from reterminal.providers.activities import ActivitiesProvider
from reterminal.providers.events import EventsProvider
from reterminal.providers.missions import MissionsProvider
from reterminal.scenes import SceneSpec


class _FakeDevice:
    """Minimal DisplayDevice stub for capturing push_pil calls."""

    def __init__(self):
        self.pushes: list[tuple[int, tuple[int, int]]] = []
        self.prepared = 0

    def prepare_push_cycle(self):
        self.prepared += 1

    def push_pil(self, image, slot):
        self.pushes.append((slot, image.size))

    def show_slot(self, slot):
        pass

    def discover_capabilities(self):
        class C:
            page_slots = 4
            host = "test-host"
        return C()


def test_bitmap_cache_detects_first_push_and_stable_state():
    cache = _BitmapCache()
    img1 = Image.new("1", (10, 10), 1)
    img2 = Image.new("1", (10, 10), 1)
    img_diff = Image.new("1", (10, 10), 0)

    assert cache.changed(0, img1) is True
    assert cache.changed(0, img2) is False
    assert cache.changed(0, img_diff) is True
    assert cache.changed(0, img_diff) is False


def test_bitmap_cache_is_per_slot():
    cache = _BitmapCache()
    img = Image.new("1", (10, 10), 1)
    assert cache.changed(0, img) is True
    assert cache.changed(1, img) is True
    assert cache.changed(0, img) is False
    assert cache.changed(1, img) is False


def _write_real_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    missions = tmp_path / "missions.md"
    missions.write_text(
        "## Active\n\n### Laila\nkind: project\ntitle: STEAM\nprogress: 1 / 4 weeks\nnext: pick\n"
    )
    events = tmp_path / "events.md"
    events.write_text("## Upcoming\n\n- 2099-01-01 New Year [event]\n")
    activities = tmp_path / "activities.md"
    activities.write_text(
        "## Recent\n\n- 2026-01-01 Movie [movie]\n\n## Queue\n\n- Back to the Future [movie]\n"
    )
    return missions, events, activities


def test_publish_once_pushes_only_changed_slots(tmp_path: Path):
    missions, events, activities = _write_real_files(tmp_path)
    device = _FakeDevice()
    publisher = DisplayPublisher(
        providers=[
            MissionsProvider(path=missions),
            EventsProvider(path=events),
            ActivitiesProvider(path=activities),
        ],
        device=device,
    )
    cache = _BitmapCache()

    pushed_first = _publish_once(publisher, cache, push=True)
    assert pushed_first == 3
    assert {slot for slot, _ in device.pushes} == {1, 2, 3}

    device.pushes.clear()
    pushed_second = _publish_once(publisher, cache, push=True)
    assert pushed_second == 0
    assert device.pushes == []

    activities.write_text(
        "## Recent\n\n- 2026-02-01 New Movie [movie]\n\n## Queue\n\n- Something Else [movie]\n"
    )
    device.pushes.clear()
    pushed_third = _publish_once(publisher, cache, push=True)
    assert pushed_third == 1
    assert device.pushes[0][0] == 3


def test_publish_once_with_push_false_does_no_uploads(tmp_path: Path):
    missions, _events, _activities = _write_real_files(tmp_path)
    device = _FakeDevice()
    publisher = DisplayPublisher(
        providers=[MissionsProvider(path=missions)],
        device=device,
    )
    cache = _BitmapCache()

    pushed = _publish_once(publisher, cache, push=False)
    assert pushed == 0
    assert device.pushes == []


def test_publish_once_handles_no_scenes_gracefully(tmp_path: Path):
    publisher = DisplayPublisher(providers=[MissionsProvider(path=tmp_path / "missing.md")])
    cache = _BitmapCache()
    assert _publish_once(publisher, cache, push=False) == 0


def test_publish_once_skips_scene_without_prerendered_via_normal_renderer(tmp_path: Path):
    """Scenes from non-prerendered providers should still flow through the renderer."""

    class _StaticProvider:
        name = "static"

        def fetch(self):
            return [SceneSpec(id="x", kind="hero", title="Hello", preferred_slot=0)]

    publisher = DisplayPublisher(providers=[_StaticProvider()])
    cache = _BitmapCache()
    assert _publish_once(publisher, cache, push=False) == 0
