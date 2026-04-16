"""
reTerminal E1001 Python Client

HTTP client and CLI for Seeed reTerminal E1001 ePaper display.

Usage:
    from reterminal import ReTerminal

    rt = ReTerminal()  # Or pass a host explicitly / set RETERMINAL_HOST
    rt.status()
    rt.push_text("Hello World")
"""

from reterminal.app import DisplayPublisher, PublishResult
from reterminal.client import ReTerminal
from reterminal.config import settings, WIDTH, HEIGHT, IMAGE_BYTES
from reterminal.device import DeviceCapabilities, ReTerminalDevice, SlotSnapshot
from reterminal.diagnostics import (
    DoctorReport,
    DiscoveryResult,
    build_discovery_candidates,
    discover_hosts,
    run_doctor,
)
from reterminal.encoding import image_to_raw, pil_to_raw, raw_to_pil
from reterminal.exceptions import ReTerminalError, ConnectionError, ImageError
from reterminal.providers import FileSceneProvider, PaperclipSceneProvider, SystemSceneProvider
from reterminal.render import MonoRenderer
from reterminal.scheduler import PriorityScheduler, SlotAssignment
from reterminal.scenes import Metric, SceneSpec
from reterminal.version import __version__

__all__ = [
    "__version__",
    "ReTerminal",
    "ReTerminalDevice",
    "SlotSnapshot",
    "DeviceCapabilities",
    "DisplayPublisher",
    "PublishResult",
    "SceneSpec",
    "Metric",
    "MonoRenderer",
    "PriorityScheduler",
    "SlotAssignment",
    "FileSceneProvider",
    "PaperclipSceneProvider",
    "SystemSceneProvider",
    "DoctorReport",
    "DiscoveryResult",
    "build_discovery_candidates",
    "discover_hosts",
    "run_doctor",
    "settings",
    "WIDTH",
    "HEIGHT",
    "IMAGE_BYTES",
    "image_to_raw",
    "pil_to_raw",
    "raw_to_pil",
    "ReTerminalError",
    "ConnectionError",
    "ImageError",
]
