"""Pull-mode publisher: render scenes to a local cache and serve them.

The reTerminal firmware deep-sleeps most of the time and wakes every
30 min to poll us for content. This module:

- Watches the manifest's family/*.md paths via FSEvents
- Renders changed slots into an in-memory bitmap cache
- Serves `GET /content-hash` and `GET /content/slot-N` so the device
  can fetch only what changed on its next wake.

There is no push to the device from here. The push pipeline that
existed for the old always-on firmware is gone; the device is the
HTTP client now, this module is the HTTP server.
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

from loguru import logger
from PIL import Image
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from reterminal.app.publisher import DisplayPublisher
from reterminal.encoding import pil_to_raw
from reterminal.protocols import DisplayDevice
from reterminal.providers import SceneProvider, build_providers, load_manifest
from reterminal.providers.manifest import FeedManifest
from reterminal.render import MonoRenderer
from reterminal.scheduler import PriorityScheduler


SANITY_TICK_SECONDS = 300
CONTENT_SERVER_PORT = 8765
RecoverDevice = Callable[[DisplayDevice], bool]


@dataclass(slots=True)
class _BitmapCache:
    """In-memory bitmap + hash per slot. The content-server endpoint reads
    from this; FSEvents writes to it via _render_to_cache.
    """

    digests: dict[int, str] = field(default_factory=dict)
    bitmaps: dict[int, bytes] = field(default_factory=dict)

    @staticmethod
    def image_digest(image: Image.Image) -> str:
        return hashlib.sha256(pil_to_raw(image)).hexdigest()

    def changed(self, slot: int, digest: str) -> bool:
        return self.digests.get(slot) != digest

    def mark_current(self, slot: int, digest: str, raw: bytes) -> None:
        self.digests[slot] = digest
        self.bitmaps[slot] = raw


def _provider_paths(manifest: FeedManifest) -> list[Path]:
    return [p for entry in manifest.providers if (p := entry.path()) is not None]


def _make_content_handler(cache: _BitmapCache) -> type[BaseHTTPRequestHandler]:
    """Serve /content-hash + /content/slot-N to the deep-sleeping device."""

    class _ContentHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
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
    threading.Thread(target=server.serve_forever, name="content-server", daemon=True).start()
    logger.info(f"live: content-server listening on 0.0.0.0:{port}")
    return server


class _DebouncedTrigger:
    """Coalesce burst FSEvents into a single tick. Editors that write-then-
    rename fire several events within milliseconds.
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
            logger.exception("live tick failed")


class _PathHandler(FileSystemEventHandler):
    def __init__(self, watched: set[str], trigger: _DebouncedTrigger):
        super().__init__()
        self._watched = watched
        self._trigger = trigger

    def on_any_event(self, event: FileSystemEvent) -> None:
        for candidate in (getattr(event, "src_path", None), getattr(event, "dest_path", None)):
            if candidate and candidate in self._watched:
                self._trigger.fire()
                return


def _render_to_cache(publisher: DisplayPublisher, cache: _BitmapCache) -> int:
    """Render assigned scenes, update the cache. Pure local work — the device
    is asleep and pulls from us when it wakes. Returns count of slots changed.
    """
    scenes = publisher._collect_scenes()
    if not scenes:
        return 0
    slot_count = publisher._resolve_slot_count()
    assignments = publisher.scheduler.assign(scenes, slot_count)
    changed = 0
    for slot, assignment in sorted(assignments.items()):
        image = publisher.renderer.render(
            assignment.scene, slot=slot, total_slots=slot_count
        )
        raw = pil_to_raw(image)
        digest = cache.image_digest(image)
        if not cache.changed(slot, digest):
            continue
        cache.mark_current(slot, digest, raw)
        changed += 1
    return changed


def _publish_once(
    publisher: DisplayPublisher,
    cache: _BitmapCache,
    *,
    push: bool = False,
    recover_device: RecoverDevice | None = None,
    tracker: object | None = None,
) -> int:
    """Backward-compat wrapper for tests. push/recover/tracker are ignored —
    the device is the HTTP client now. Returns slots changed.
    """
    del push, recover_device, tracker
    return _render_to_cache(publisher, cache)


def run_live(
    manifest_path: Path,
    *,
    device: DisplayDevice | None = None,
    push: bool = False,
    sanity_tick_seconds: int = SANITY_TICK_SECONDS,
    on_tick: Callable[[int], None] | None = None,
    recover_device: RecoverDevice | None = None,
) -> None:
    """FSEvents-driven render loop + content-server. Blocks until KeyboardInterrupt.

    device / push / recover_device are accepted for CLI signature compatibility
    but ignored — this is pull-only now. The device is the HTTP client.
    """
    del device, push, recover_device

    manifest = load_manifest(manifest_path)
    providers: Sequence[SceneProvider] = build_providers(manifest)
    publisher = DisplayPublisher(
        providers=providers,
        renderer=MonoRenderer(),
        scheduler=PriorityScheduler(),
    )
    cache = _BitmapCache()
    content_server = _start_content_server(cache)

    # Initial render — populates the cache before the device's first poll.
    initial = _render_to_cache(publisher, cache)
    logger.info(f"live: rendered {initial} slot(s) into cache")

    def tick() -> None:
        changed = _render_to_cache(publisher, cache)
        if changed:
            logger.info(f"live: re-rendered {changed} slot(s)")
        if on_tick is not None:
            on_tick(changed)

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
