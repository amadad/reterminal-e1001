"""FSEvents-driven publish loop for the kitchen-display pipeline.

Replaces the polling `--interval` model. When any file referenced by a
manifest provider changes, that slot re-renders and the resulting bitmap
is compared in-memory to the last one we pushed; the device receives a new
upload only when the bitmap is actually different.

Trigger sources:

- FSEvents (via watchdog) on the parent directory of every provider's
  source file — covers atomic-write replacements (which often delete +
  recreate, which fire events on the directory not the file).
- A slow sanity tick (default 5 min) catches any FSEvent the OS dropped
  and gives time-based providers a heartbeat in case they ever appear.

There is no per-slot SHA cache on disk. The device persists what it shows
in LittleFS; the only persistent state we keep here is what the launchd
log captures.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests
from loguru import logger
from PIL import Image
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from reterminal.app.publisher import DisplayPublisher
from reterminal.encoding import pil_to_raw
from reterminal.device.capabilities import DeviceCapabilities
from reterminal.exceptions import ConnectionError as DeviceConnectionError, ReTerminalError
from reterminal.protocols import DisplayDevice
from reterminal.providers import SceneProvider, build_providers, load_manifest
from reterminal.providers.manifest import FeedManifest
from reterminal.render import MonoRenderer
from reterminal.scheduler import PriorityScheduler


SANITY_TICK_SECONDS = 300
CONTENT_SERVER_PORT = 8765
RecoverDevice = Callable[[DisplayDevice], bool]


def _is_connection_failure(exc: BaseException) -> bool:
    return isinstance(exc, DeviceConnectionError)


@dataclass(slots=True)
class _OnlineTracker:
    """Track online/offline transitions so we log once per state change.

    Without this, a multi-hour outage produced thousands of identical
    'device unavailable' warnings — one set per retry per slot per tick.
    """

    is_online: bool = True
    offline_since: float | None = None

    def mark_offline(self, reason: str) -> None:
        if self.is_online:
            self.is_online = False
            self.offline_since = time.monotonic()
            logger.warning(f"live: device went offline: {reason}")

    def mark_online(self) -> None:
        if not self.is_online:
            duration = (
                time.monotonic() - self.offline_since
                if self.offline_since is not None
                else 0.0
            )
            self.is_online = True
            self.offline_since = None
            logger.info(f"live: device back online after {duration:.0f}s offline")


def _try_recover_device(
    device: DisplayDevice,
    recover_device: RecoverDevice | None,
    tracker: _OnlineTracker | None = None,
) -> bool:
    if recover_device is None:
        return False
    try:
        recovered = recover_device(device)
        if recovered and tracker is not None:
            tracker.mark_online()
        return recovered
    except Exception as exc:
        logger.debug(f"live: device rediscovery failed: {exc}")
        if tracker is not None:
            tracker.mark_offline(f"rediscovery error: {exc}")
        return False


@dataclass(slots=True)
class _BitmapCache:
    """In-memory record of the last bitmap known to be on each slot.

    Retains the raw 48000-byte bitmap per slot so a battery-powered device
    can poll us instead of having us push. Bitmaps live in process memory
    only; they are reseeded from the device's /snapshot on startup.
    """

    digests: dict[int, str] = field(default_factory=dict)
    bitmaps: dict[int, bytes] = field(default_factory=dict)
    device_uptime_ms: int | None = None

    @staticmethod
    def image_digest(image: Image.Image) -> str:
        return hashlib.sha256(pil_to_raw(image)).hexdigest()

    @staticmethod
    def raw_digest(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    def changed(self, slot: int, digest: str) -> bool:
        return self.digests.get(slot) != digest

    def mark_current(self, slot: int, digest: str, raw: bytes | None = None) -> None:
        self.digests[slot] = digest
        if raw is not None:
            self.bitmaps[slot] = raw

    def seed_raw(self, slot: int, raw: bytes) -> None:
        self.mark_current(slot, self.raw_digest(raw), raw)


def _provider_paths(manifest: FeedManifest) -> list[Path]:
    """Pull `path` config values out of the manifest for FSEvents wiring."""
    return [p for entry in manifest.providers if (p := entry.path()) is not None]


def _make_content_handler(cache: _BitmapCache) -> type[BaseHTTPRequestHandler]:
    """Serve /content-hash and /content/slot-N so a deep-sleeping device can pull.

    Lives in the publisher because the publisher is the source of truth for what
    every slot should contain. The device polls this on each wake; only fetches
    body bytes when the hash actually changed.
    """

    class _ContentHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:  # noqa: D401
            logger.debug("content-server: " + fmt, *args)

        def _send_json(self, code: int, body: dict[str, object]) -> None:
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/content-hash":
                hashes = {f"slot-{slot}": cache.digests.get(slot) for slot in range(4)}
                self._send_json(200, {"hashes": hashes})
                return
            if self.path.startswith("/content/slot-"):
                try:
                    slot = int(self.path.rsplit("-", 1)[-1])
                except ValueError:
                    self._send_json(400, {"error": "bad slot"})
                    return
                data = cache.bitmaps.get(slot)
                if data is None:
                    self._send_json(404, {"error": "no bitmap", "slot": slot})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Slot", str(slot))
                self.send_header("X-Hash", cache.digests.get(slot, ""))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json(404, {"error": "not found", "path": self.path})

    return _ContentHandler


def _start_content_server(cache: _BitmapCache, port: int = CONTENT_SERVER_PORT) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), _make_content_handler(cache))
    thread = threading.Thread(target=server.serve_forever, name="content-server", daemon=True)
    thread.start()
    logger.info(f"live: content-server listening on 0.0.0.0:{port}")
    return server


class _DebouncedTrigger:
    """Coalesce a burst of FSEvents into a single wake-up.

    Editors often write-then-rename, which fires modify+create+move events
    in a few ms. Without debounce the publisher would render the same file
    three times back-to-back.
    """

    def __init__(self, callback: Callable[[], None], delay: float = 0.5):
        self._callback = callback
        self._delay = delay
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def fire(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._invoke)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _invoke(self) -> None:
        with self._lock:
            self._timer = None
        try:
            self._callback()
        except Exception:
            logger.exception("live publish tick failed")


class _PathHandler(FileSystemEventHandler):
    """Fire the trigger when any of a known set of paths is touched."""

    def __init__(self, watched: set[str], trigger: _DebouncedTrigger):
        super().__init__()
        self._watched = watched
        self._trigger = trigger

    def on_any_event(self, event: FileSystemEvent) -> None:
        # watchdog's event paths come back as str on darwin
        src = getattr(event, "src_path", None)
        dest = getattr(event, "dest_path", None)
        for candidate in (src, dest):
            if candidate and candidate in self._watched:
                self._trigger.fire()
                return


def _seed_cache_from_device(
    device: DisplayDevice,
    cache: _BitmapCache,
    *,
    caps: DeviceCapabilities | None = None,
) -> int:
    """Seed slot digests from firmware snapshot readback when available."""
    snapshot = getattr(device, "snapshot", None)
    if snapshot is None:
        return 0

    if caps is None:
        try:
            caps = device.discover_capabilities(refresh=True)
        except (DeviceConnectionError, requests.RequestException, OSError):
            logger.debug("live: could not refresh capabilities before snapshot seeding", exc_info=True)
            return 0

    if caps.loaded_pages:
        slots = [slot for slot, loaded in enumerate(caps.loaded_pages[: caps.page_slots]) if loaded]
    else:
        slots = list(range(caps.page_slots))

    seeded = 0
    for slot in slots:
        try:
            slot_snapshot = snapshot(slot)
        except (DeviceConnectionError, requests.RequestException, OSError, ReTerminalError):
            logger.debug(f"live: could not seed slot {slot} from snapshot", exc_info=True)
            continue
        cache.seed_raw(slot, slot_snapshot.raw)
        seeded += 1
    return seeded


def _sync_cache_with_device(
    device: DisplayDevice,
    cache: _BitmapCache,
    *,
    seed_snapshots: bool = False,
    recover_device: RecoverDevice | None = None,
    tracker: _OnlineTracker | None = None,
) -> int:
    """Refresh device state and invalidate digest cache after a reboot."""
    try:
        caps = device.prepare_push_cycle()
    except (DeviceConnectionError, requests.RequestException, ReTerminalError) as exc:
        if not _is_connection_failure(exc):
            logger.debug("live: could not refresh device state before publish", exc_info=True)
            return 0
        if tracker is not None:
            tracker.mark_offline(f"prepare_push_cycle: {exc}")
        if not _try_recover_device(device, recover_device, tracker):
            return 0
        try:
            caps = device.prepare_push_cycle()
        except (DeviceConnectionError, requests.RequestException, ReTerminalError) as retry_exc:
            logger.debug(f"live: device still unavailable after rediscovery: {retry_exc}")
            return 0

    if tracker is not None:
        tracker.mark_online()

    uptime_ms = caps.uptime_ms
    rebooted = (
        isinstance(cache.device_uptime_ms, int)
        and isinstance(uptime_ms, int)
        and uptime_ms < cache.device_uptime_ms
    )
    if rebooted:
        cache.digests.clear()
        seed_snapshots = True
        logger.info("live: device uptime reset; cleared slot digest cache")

    if isinstance(uptime_ms, int):
        cache.device_uptime_ms = uptime_ms

    if seed_snapshots:
        return _seed_cache_from_device(device, cache, caps=caps)
    return 0


def _publish_once(
    publisher: DisplayPublisher,
    cache: _BitmapCache,
    *,
    push: bool,
    recover_device: RecoverDevice | None = None,
    tracker: _OnlineTracker | None = None,
) -> int:
    """Render one publish cycle and push only the slots whose bitmap changed.

    Returns the number of slots actually pushed.
    """
    if push and publisher.device is not None:
        _sync_cache_with_device(
            publisher.device, cache, recover_device=recover_device, tracker=tracker
        )

    scenes = publisher._collect_scenes()
    if not scenes:
        return 0
    slot_count = publisher._resolve_slot_count()
    assignments = publisher.scheduler.assign(scenes, slot_count)
    pushed = 0
    for slot, assignment in sorted(assignments.items()):
        image = publisher.renderer.render(
            assignment.scene, slot=slot, total_slots=slot_count
        )
        raw = pil_to_raw(image)
        digest = cache.image_digest(image)
        if not cache.changed(slot, digest):
            continue
        if push and publisher.device is not None:
            try:
                publisher.device.push_pil(image, slot)
            except (DeviceConnectionError, requests.RequestException, ReTerminalError) as exc:
                if not _is_connection_failure(exc):
                    raise
                if tracker is not None:
                    tracker.mark_offline(f"slot {slot} upload: {exc}")
                if not _try_recover_device(publisher.device, recover_device, tracker):
                    return pushed
                _sync_cache_with_device(
                    publisher.device,
                    cache,
                    seed_snapshots=True,
                    recover_device=recover_device,
                    tracker=tracker,
                )
                try:
                    publisher.device.push_pil(image, slot)
                except (DeviceConnectionError, requests.RequestException, ReTerminalError) as retry_exc:
                    if not _is_connection_failure(retry_exc):
                        raise
                    logger.debug(
                        f"live: slot {slot} upload still failed after rediscovery: {retry_exc}"
                    )
                    return pushed
            cache.mark_current(slot, digest, raw)
            pushed += 1
        elif not push:
            cache.mark_current(slot, digest, raw)
    return pushed


def run_live(
    manifest_path: Path,
    *,
    device: DisplayDevice | None = None,
    push: bool = False,
    sanity_tick_seconds: int = SANITY_TICK_SECONDS,
    on_tick: Callable[[int], None] | None = None,
    recover_device: RecoverDevice | None = None,
) -> None:
    """Start the FSEvents-driven publish loop. Runs until KeyboardInterrupt.

    Blocks. Designed to be the body of `reterminal publish --watch`.

    Args:
        manifest_path: Path to a provider manifest JSON.
        device: Adapter to push pixels to; required when push=True.
        push: If True, send changed slots to the device. False = dry-run.
        sanity_tick_seconds: Time-based fallback in case an FSEvent is missed.
        on_tick: Optional callback invoked with the slot count pushed each tick
            (for tests and logging).
    """
    manifest = load_manifest(manifest_path)
    providers: Sequence[SceneProvider] = build_providers(manifest)
    publisher = DisplayPublisher(
        providers=providers,
        renderer=MonoRenderer(),
        scheduler=PriorityScheduler(),
        device=device,
    )
    cache = _BitmapCache()
    tracker = _OnlineTracker()
    content_server = _start_content_server(cache)
    if push and device is not None:
        seeded = _sync_cache_with_device(
            device,
            cache,
            seed_snapshots=True,
            recover_device=recover_device,
            tracker=tracker,
        )
        if seeded:
            logger.info(f"live: seeded {seeded} slot digest(s) from device snapshots")

    def tick() -> None:
        pushed = _publish_once(
            publisher, cache, push=push, recover_device=recover_device, tracker=tracker
        )
        if pushed:
            logger.info(f"live: pushed {pushed} slot(s)")
        if on_tick is not None:
            on_tick(pushed)

    trigger = _DebouncedTrigger(tick, delay=0.5)

    paths = _provider_paths(manifest)
    watched = {str(p.resolve()) for p in paths if p.exists() or p.parent.exists()}
    observer = Observer()
    handler = _PathHandler(watched, trigger)
    seen_dirs: set[str] = set()
    for p in paths:
        parent = p.parent
        if parent.exists() and str(parent) not in seen_dirs:
            observer.schedule(handler, str(parent), recursive=False)
            seen_dirs.add(str(parent))
    observer.start()
    logger.info(
        f"live: watching {len(watched)} path(s) across {len(seen_dirs)} dir(s); "
        f"sanity tick every {sanity_tick_seconds}s"
    )

    try:
        # Initial publish so the device reflects current state immediately.
        tick()
        while True:
            time.sleep(sanity_tick_seconds)
            tick()
    except KeyboardInterrupt:
        logger.info("live: stopped")
    finally:
        trigger.cancel()
        observer.stop()
        observer.join()
        content_server.shutdown()
        content_server.server_close()

