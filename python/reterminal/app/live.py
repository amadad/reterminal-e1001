"""Pull-mode publisher: render scenes to a local cache and serve them.

The reTerminal firmware deep-sleeps most of the time and wakes every
30 min to poll us for content. This module:

- Watches every local source path declared by the provider manifest
- Watches the manifest file itself and rebuilds providers in place when
  it changes, so repointing a path does not require a daemon restart
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
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from loguru import logger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from reterminal.app.publisher import DisplayPublisher
from reterminal.config import SLOT_COUNT
from reterminal.encoding import pil_to_raw
from reterminal.providers import build_providers, load_manifest
from reterminal.providers.manifest import FeedManifest
from reterminal.render import MonoRenderer
from reterminal.scheduler import PriorityScheduler


SANITY_TICK_SECONDS = 300
CONTENT_SERVER_PORT = 8765
CONTENT_SERVER_REQUEST_TIMEOUT = 5.0


@dataclass(frozen=True, slots=True)
class _BitmapEntry:
    digest: str
    raw: bytes


@dataclass(slots=True)
class _BitmapCache:
    """In-memory bitmap + hash per slot. The content-server endpoint reads
    from this; FSEvents writes to it via _render_to_cache.
    """

    _entries: dict[int, _BitmapEntry] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def changed(self, slot: int, digest: str) -> bool:
        with self._lock:
            entry = self._entries.get(slot)
            return entry is None or entry.digest != digest

    def mark_current(self, slot: int, digest: str, raw: bytes) -> None:
        with self._lock:
            self._entries[slot] = _BitmapEntry(digest=digest, raw=raw)

    def entry(self, slot: int) -> _BitmapEntry | None:
        with self._lock:
            return self._entries.get(slot)

    def hashes(self) -> dict[str, str | None]:
        with self._lock:
            return {
                f"slot-{slot}": (
                    self._entries[slot].digest if slot in self._entries else None
                )
                for slot in range(SLOT_COUNT)
            }


def _provider_paths(manifest: FeedManifest) -> list[Path]:
    paths: list[Path] = []
    for entry in manifest.providers:
        for p in entry.source_paths():
            if p not in paths:
                paths.append(p)
    return paths


def _build_publisher(manifest: FeedManifest) -> DisplayPublisher:
    return DisplayPublisher(
        providers=build_providers(manifest),
        renderer=MonoRenderer(),
        scheduler=PriorityScheduler(),
    )


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
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/content-hash":
                self._send_json(200, {"hashes": cache.hashes()})
                return
            if self.path.startswith("/content/slot-"):
                try:
                    slot = int(self.path.rsplit("-", 1)[-1])
                except ValueError:
                    self._send_json(400, {"error": "bad slot"})
                    return
                entry = cache.entry(slot)
                if entry is None:
                    self._send_json(404, {"error": "no bitmap", "slot": slot})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(entry.raw)))
                self.send_header("X-Slot", str(slot))
                self.send_header("X-Hash", entry.digest)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(entry.raw)
                self.close_connection = True
                return
            self._send_json(404, {"error": "not found", "path": self.path})

    return _ContentHandler


class _ContentServer(ThreadingHTTPServer):
    """Small LAN server hardened for sleepy clients.

    The panel wakes briefly and may disappear mid-request. Bound connection
    lifetime so stale sockets cannot consume the small accept backlog.
    """

    daemon_threads = True
    request_queue_size = 32
    allow_reuse_address = True

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        request, client_address = super().get_request()
        request.settimeout(CONTENT_SERVER_REQUEST_TIMEOUT)
        return request, client_address


def _start_content_server(cache: _BitmapCache, port: int = CONTENT_SERVER_PORT) -> ThreadingHTTPServer:
    server = _ContentServer(("0.0.0.0", port), _make_content_handler(cache))
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
    """Fire `trigger` when an event touches a path `matches` accepts.

    `matches` is evaluated per event rather than closing over a fixed set so
    the watched paths can change underneath us (manifest reload repoints them).
    """

    def __init__(self, matches: Callable[[str], bool], trigger: _DebouncedTrigger):
        super().__init__()
        self._matches = matches
        self._trigger = trigger

    def on_any_event(self, event: FileSystemEvent) -> None:
        for candidate in (getattr(event, "src_path", None), getattr(event, "dest_path", None)):
            if candidate and self._matches(candidate):
                self._trigger.fire()
                return


class _LiveRuntime:
    """Mutable live state: the active publisher and the content paths to watch.

    Rebuilt in place from the manifest on disk so a repointed path is picked
    up without restarting the daemon — the failure mode that left the display
    rendering "source missing" for days after a content dir moved.
    """

    def __init__(self, manifest_path: Path, cache: _BitmapCache):
        self.manifest_path = manifest_path
        self.cache = cache
        self.content_watched: set[str] = set()
        self.content_paths: list[Path] = []
        manifest = load_manifest(manifest_path)
        self.publisher = _build_publisher(manifest)
        self._set_watched(manifest)

    def _set_watched(self, manifest: FeedManifest) -> None:
        paths = _provider_paths(manifest)
        self.content_paths = paths
        self.content_watched = {
            str(p.resolve()) for p in paths if p.exists() or p.parent.exists()
        }

    def render(self) -> int:
        return _render_to_cache(self.publisher, self.cache)

    def reload(self) -> bool:
        """Rebuild publisher + watched paths from the manifest on disk. Returns
        False (keeping the previous config) if the manifest is unreadable, so a
        mid-edit save never takes the display down.
        """
        try:
            manifest = load_manifest(self.manifest_path)
            publisher = _build_publisher(manifest)
        except Exception:
            logger.exception("live: manifest reload failed; keeping previous config")
            return False
        self.publisher = publisher
        self._set_watched(manifest)
        return True


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
        digest = hashlib.sha256(raw).hexdigest()
        if not cache.changed(slot, digest):
            continue
        cache.mark_current(slot, digest, raw)
        changed += 1
    return changed


def run_live(
    manifest_path: Path,
    *,
    sanity_tick_seconds: int = SANITY_TICK_SECONDS,
    on_tick: Callable[[int], None] | None = None,
) -> None:
    """Run the FSEvents renderer and LAN content server until interrupted."""

    manifest_path = manifest_path.resolve()
    cache = _BitmapCache()
    runtime = _LiveRuntime(manifest_path, cache)
    content_server = _start_content_server(cache)

    # Initial render — populates the cache before the device's first poll.
    initial = runtime.render()
    logger.info(f"live: rendered {initial} slot(s) into cache")

    observer = Observer()
    seen_dirs: set[str] = set()

    def _schedule_content_dirs(handler: _PathHandler) -> None:
        for p in runtime.content_paths:
            parent = str(p.parent)
            if p.parent.exists() and parent not in seen_dirs:
                observer.schedule(handler, parent, recursive=False)
                seen_dirs.add(parent)

    def tick() -> None:
        changed = runtime.render()
        if changed:
            logger.info(f"live: re-rendered {changed} slot(s)")
        if on_tick is not None:
            on_tick(changed)

    trigger = _DebouncedTrigger(tick, delay=0.5)
    content_handler = _PathHandler(lambda p: p in runtime.content_watched, trigger)

    def reload_manifest() -> None:
        if not runtime.reload():
            return
        # A repointed path may live in a not-yet-watched dir.
        _schedule_content_dirs(content_handler)
        logger.info(
            f"live: manifest reloaded; watching {len(runtime.content_watched)} content path(s)"
        )
        tick()

    reload_trigger = _DebouncedTrigger(reload_manifest, delay=0.5)
    manifest_str = str(manifest_path)
    manifest_handler = _PathHandler(lambda p: p == manifest_str, reload_trigger)

    _schedule_content_dirs(content_handler)
    # Always schedule the manifest handler (a distinct handler object), even if
    # its parent dir is already watched for content — watchdog fans events to
    # every handler registered on a dir.
    observer.schedule(manifest_handler, str(manifest_path.parent), recursive=False)
    observer.start()
    watched_dirs = len(seen_dirs | {str(manifest_path.parent)})
    logger.info(
        f"live: watching {len(runtime.content_watched)} content path(s) + manifest "
        f"across {watched_dirs} dir(s); sanity tick every {sanity_tick_seconds}s"
    )

    try:
        while True:
            time.sleep(sanity_tick_seconds)
            tick()
    except KeyboardInterrupt:
        logger.info("live: stopped")
    finally:
        trigger.cancel()
        reload_trigger.cancel()
        observer.stop()
        observer.join()
        content_server.shutdown()
        content_server.server_close()
