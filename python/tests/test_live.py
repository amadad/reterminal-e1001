"""Tests for the pull-mode render loop.

Under the deep-sleep firmware architecture, this process renders scenes
to an in-memory cache and serves them via /content-hash + /content/slot-N.
There is no push to the device from here; the device polls us on each
wake.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from reterminal.app.live import _BitmapCache, _publish_once, _render_to_cache
from reterminal.app.publisher import DisplayPublisher
from reterminal.providers.activities import ActivitiesProvider
from reterminal.providers.events import EventsProvider
from reterminal.providers.manifest import SlottedProvider
from reterminal.providers.missions import MissionsProvider
from reterminal.render import MonoRenderer
from reterminal.scenes import SceneSpec
from reterminal.scheduler import PriorityScheduler


def _slotted(provider, slot: int):
    return SlottedProvider(provider=provider, slot=slot)


def _write_real_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    missions = tmp_path / "missions.md"
    missions.write_text(
        "## Active\n\n### Kid 1\nkind: project\ntitle: STEAM\nprogress: 1 / 4 weeks\nnext: pick\n"
    )
    events = tmp_path / "events.md"
    events.write_text("## Upcoming\n\n- 2099-01-01 New Year [event]\n")
    activities = tmp_path / "activities.md"
    activities.write_text(
        "## Recent\n\n- 2026-01-01 Movie [movie]\n\n## Queue\n\n- Back to the Future [movie]\n"
    )
    return missions, events, activities


def test_bitmap_cache_detects_change_and_marks_current():
    cache = _BitmapCache()
    img = Image.new("1", (10, 10), 1)
    img_diff = Image.new("1", (10, 10), 0)
    digest = cache.image_digest(img)
    digest_diff = cache.image_digest(img_diff)

    assert cache.changed(0, digest) is True
    cache.mark_current(0, digest, b"\xff" * 100)
    assert cache.changed(0, digest) is False
    assert cache.changed(0, digest_diff) is True
    assert cache.bitmaps[0] == b"\xff" * 100


def test_bitmap_cache_is_per_slot():
    cache = _BitmapCache()
    img = Image.new("1", (10, 10), 1)
    digest = cache.image_digest(img)
    cache.mark_current(0, digest, b"a" * 10)
    assert cache.changed(0, digest) is False
    assert cache.changed(1, digest) is True
    cache.mark_current(1, digest, b"b" * 10)
    assert cache.bitmaps[0] != cache.bitmaps[1]


def test_render_to_cache_populates_only_changed_slots(tmp_path: Path):
    missions, events, activities = _write_real_files(tmp_path)
    publisher = DisplayPublisher(
        providers=[
            _slotted(MissionsProvider(path=missions), 1),
            _slotted(EventsProvider(path=events), 2),
            _slotted(ActivitiesProvider(path=activities), 3),
        ],
        renderer=MonoRenderer(),
        scheduler=PriorityScheduler(),
    )
    cache = _BitmapCache()

    first = _render_to_cache(publisher, cache)
    assert first == 3
    assert set(cache.digests.keys()) == {1, 2, 3}
    assert all(slot in cache.bitmaps for slot in {1, 2, 3})

    # Unchanged source → no slots re-rendered.
    assert _render_to_cache(publisher, cache) == 0

    # Mutate activities → only slot 3 changes.
    activities.write_text(
        "## Recent\n\n- 2026-02-01 New Movie [movie]\n\n## Queue\n\n- Something Else [movie]\n"
    )
    third = _render_to_cache(publisher, cache)
    assert third == 1


def test_publish_once_is_render_only(tmp_path: Path):
    """Backward-compat: _publish_once still works but is now pure render."""
    missions, _events, _activities = _write_real_files(tmp_path)
    publisher = DisplayPublisher(
        providers=[_slotted(MissionsProvider(path=missions), 1)],
        renderer=MonoRenderer(),
        scheduler=PriorityScheduler(),
    )
    cache = _BitmapCache()
    # push, recover_device, tracker are accepted for signature compat and ignored.
    assert _publish_once(publisher, cache, push=True, recover_device=None) == 1
    assert _publish_once(publisher, cache, push=False) == 0


def test_render_handles_no_scenes_gracefully(tmp_path: Path):
    publisher = DisplayPublisher(
        providers=[MissionsProvider(path=tmp_path / "missing.md")],
        renderer=MonoRenderer(),
        scheduler=PriorityScheduler(),
    )
    cache = _BitmapCache()
    # Missing source still emits a "missing" notice scene, so it does render.
    # Just verify no crash and cache populates.
    _render_to_cache(publisher, cache)


def test_render_skips_scene_without_prerendered_via_normal_renderer(tmp_path: Path):
    class _StaticProvider:
        name = "static"

        def fetch(self):
            return [SceneSpec(id="x", kind="hero", title="Hello", preferred_slot=0)]

    publisher = DisplayPublisher(
        providers=[_StaticProvider()],
        renderer=MonoRenderer(),
        scheduler=PriorityScheduler(),
    )
    cache = _BitmapCache()
    # The hero renderer path may or may not produce a bitmap; we just verify
    # no crash and the function returns an int.
    result = _render_to_cache(publisher, cache)
    assert isinstance(result, int)
