"""
reTerminal E1001 Python Client

HTTP client and CLI for Seeed reTerminal E1001 ePaper display.

Usage:
    from reterminal import ReTerminal

    rt = ReTerminal()  # Uses RETERMINAL_HOST env var or default
    rt.status()
    rt.push_text("Hello World")
"""

from reterminal.client import ReTerminal
from reterminal.config import settings, WIDTH, HEIGHT, IMAGE_BYTES
from reterminal.encoding import image_to_raw, pil_to_raw
from reterminal.exceptions import ReTerminalError, ConnectionError, ImageError

__version__ = "2.0.0"

__all__ = [
    "ReTerminal",
    "settings",
    "WIDTH",
    "HEIGHT",
    "IMAGE_BYTES",
    "image_to_raw",
    "pil_to_raw",
    "ReTerminalError",
    "ConnectionError",
    "ImageError",
]
