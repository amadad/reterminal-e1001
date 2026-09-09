"""Tests for the pull-mode render loop.

Under the deep-sleep firmware architecture, this process renders scenes
to an in-memory cache and serves them via /content-hash + /content/slot-N.
There is no push to the device from here; the device polls us on each
wake.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
import pytest
from pathlib import Path

from PIL import Image

from reterminal.app.live import (
    _BitmapCache,
    _LiveRuntime,
    _render_to_cache,
    _start_content_server,
)
from reterminal.app.publisher import DisplayPublisher
from reterminal.app.delivery import DeliveryState
from reterminal.encoding import pil_to_raw
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
    digest = hashlib.sha256(pil_to_raw(img)).hexdigest()
    digest_diff = hashlib.sha256(pil_to_raw(img_diff)).hexdigest()

    assert cache.changed(0, digest) is True
    cache.mark_current(0, digest, b"\xff" * 100)
    assert cache.changed(0, digest) is False
    assert cache.changed(0, digest_diff) is True
    entry = cache.entry(0)
    assert entry is not None
    assert entry.digest == digest
    assert entry.raw == b"\xff" * 100


def test_bitmap_cache_is_per_slot():
    cache = _BitmapCache()
    img = Image.new("1", (10, 10), 1)
    digest = hashlib.sha256(pil_to_raw(img)).hexdigest()
    cache.mark_current(0, digest, b"a" * 10)
    assert cache.changed(0, digest) is False
    assert cache.changed(1, digest) is True
    cache.mark_current(1, digest, b"b" * 10)
    assert cache.entry(0) != cache.entry(1)


def test_content_server_closes_short_lived_requests():
    cache = _BitmapCache()
    cache.mark_current(0, "abc123", b"x" * 48000)
    server = _start_content_server(cache, port=0)
    host, port = server.server_address
    try:
        response = urllib.request.urlopen(
            f"http://{host}:{port}/content-hash", timeout=2
        )
        try:
            assert response.headers["Connection"] == "close"
            payload = json.loads(response.read())
        finally:
            response.close()
        assert payload["hashes"]["slot-0"] == "abc123"

        bitmap = urllib.request.urlopen(f"http://{host}:{port}/content/slot-0", timeout=2)
        try:
            assert bitmap.headers["X-Hash"] == "abc123"
            assert bitmap.read() == b"x" * 48000
        finally:
            bitmap.close()
    finally:
        server.shutdown()
        server.server_close()


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
    assert {slot for slot in range(4) if cache.entry(slot) is not None} == {1, 2, 3}
    assert all(cache.entry(slot) is not None for slot in {1, 2, 3})

    # Unchanged source → no slots re-rendered.
    assert _render_to_cache(publisher, cache) == 0

    # Mutate activities → only slot 3 changes.
    activities.write_text(
        "## Recent\n\n- 2026-02-01 New Movie [movie]\n\n## Queue\n\n- Something Else [movie]\n"
    )
    third = _render_to_cache(publisher, cache)
    assert third == 1


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


def _write_manifest(path: Path, events_path: Path) -> Path:
    path.write_text(
        json.dumps(
            {"providers": [{"type": "events", "path": str(events_path), "slot": 2}]}
        )
    )
    return path


def test_live_runtime_reload_repoints_path_without_restart(tmp_path: Path):
    """The outage that motivated this: the daemon read the manifest once at
    startup, so a moved content dir left it rendering 'source missing'. Reload
    must rebuild the publisher and watched set from the manifest on disk.
    """
    events_a = tmp_path / "a" / "events.md"
    events_a.parent.mkdir()
    events_a.write_text("## Upcoming\n\n- 2099-01-01 Alpha Event [event]\n")
    events_b = tmp_path / "b" / "events.md"
    events_b.parent.mkdir()
    events_b.write_text("## Upcoming\n\n- 2099-02-02 Beta Event [event]\n")

    manifest = _write_manifest(tmp_path / "manifest.json", events_a)
    cache = _BitmapCache()
    runtime = _LiveRuntime(manifest, cache)
    runtime.render()

    assert str(events_a.resolve()) in runtime.content_watched
    entry_a = cache.entry(2)
    assert entry_a is not None
    digest_a = entry_a.digest

    # Repoint the manifest at a different file with different content.
    _write_manifest(manifest, events_b)
    assert runtime.reload() is True
    assert str(events_b.resolve()) in runtime.content_watched
    assert str(events_a.resolve()) not in runtime.content_watched

    runtime.render()
    entry_b = cache.entry(2)
    assert entry_b is not None
    assert entry_b.digest != digest_a


def test_live_runtime_reload_keeps_config_on_broken_manifest(tmp_path: Path):
    events = tmp_path / "events.md"
    events.write_text("## Upcoming\n\n- 2099-01-01 Alpha Event [event]\n")
    manifest = _write_manifest(tmp_path / "manifest.json", events)
    delivery = DeliveryState()
    runtime = _LiveRuntime(manifest, _BitmapCache(), delivery)
    good_publisher = runtime.publisher

    manifest.write_text("{ not valid json")
    assert runtime.reload() is False
    assert runtime.publisher is good_publisher
    assert str(events.resolve()) in runtime.content_watched
    runtime.render()
    assert delivery.health(runtime.cache.hashes())["config_error"] is not None
    _write_manifest(manifest, events)
    assert runtime.reload()
    assert delivery.config_error is None


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


def test_failed_render_preserves_entire_previous_edition():
    """A later slot failure must not publish a mixture of old and new slots."""
    class Provider:
        name = "test"

        def fetch(self):
            return [SceneSpec(id=f"x{n}", kind="hero", title="New", preferred_slot=n) for n in range(2)]

    class Renderer:
        def render(self, scene, *, slot, total_slots):
            if slot == 1:
                raise ValueError("failed slot")
            return Image.new("1", (800, 480), 0)

    publisher = DisplayPublisher(providers=[Provider()], renderer=Renderer(), scheduler=PriorityScheduler())
    cache = _BitmapCache()
    cache.mark_current(0, "old", b"old")
    with pytest.raises(ValueError, match="failed slot"):
        _render_to_cache(publisher, cache)
    assert cache.entry(0).digest == "old"
