#!/usr/bin/env python3
"""
reTerminal E1001 Python Client

Simple client for pushing images to the reTerminal E1001 ePaper display.

Usage:
    from reterminal import ReTerminal

    rt = ReTerminal("192.168.1.100")
    rt.push_text("Hello World", page=0)
    rt.push_image("photo.png", page=1)
    rt.next_page()
"""

import requests
import io
from typing import Optional, Tuple

# Display dimensions
WIDTH = 800
HEIGHT = 480
IMAGE_BYTES = WIDTH * HEIGHT // 8  # 48000 bytes


class ReTerminal:
    """Client for reTerminal E1001 HTTP API."""

    def __init__(self, host: str, timeout: int = 30):
        """
        Initialize client.

        Args:
            host: Device IP address (e.g., "192.168.1.100")
            timeout: Request timeout in seconds
        """
        self.host = host
        self.base_url = f"http://{host}"
        self.timeout = timeout

    def status(self) -> dict:
        """Get device status."""
        r = requests.get(f"{self.base_url}/status", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def buttons(self) -> dict:
        """Get button states."""
        r = requests.get(f"{self.base_url}/buttons", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def beep(self) -> bool:
        """Trigger buzzer."""
        r = requests.get(f"{self.base_url}/beep", timeout=self.timeout)
        r.raise_for_status()
        return r.json().get("beeped", False)

    def get_page(self) -> dict:
        """Get current page info."""
        r = requests.get(f"{self.base_url}/page", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def set_page(self, page: int) -> dict:
        """Set current page."""
        r = requests.post(
            f"{self.base_url}/page",
            json={"page": page},
            timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()

    def next_page(self) -> dict:
        """Navigate to next page."""
        r = requests.post(
            f"{self.base_url}/page",
            json={"action": "next"},
            timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()

    def prev_page(self) -> dict:
        """Navigate to previous page."""
        r = requests.post(
            f"{self.base_url}/page",
            json={"action": "prev"},
            timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()

    def push_raw(self, data: bytes, page: Optional[int] = None) -> dict:
        """
        Push raw 1-bit image data.

        Args:
            data: Raw bitmap data (48000 bytes, 1-bit per pixel)
            page: Page to store (0-3), or None to display immediately
        """
        if len(data) != IMAGE_BYTES:
            raise ValueError(f"Image must be {IMAGE_BYTES} bytes, got {len(data)}")

        url = f"{self.base_url}/imageraw"
        if page is not None:
            url += f"?page={page}"

        files = {"image": ("image.raw", io.BytesIO(data), "application/octet-stream")}
        r = requests.post(url, files=files, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def push_image(self, image_path: str, page: Optional[int] = None,
                   invert: bool = False, dither: bool = True) -> dict:
        """
        Convert and push an image file.

        Args:
            image_path: Path to image file (PNG, JPG, etc.)
            page: Page to store (0-3), or None to display immediately
            invert: Invert black/white
            dither: Use Floyd-Steinberg dithering for grayscale
        """
        data = image_to_raw(image_path, invert=invert, dither=dither)
        return self.push_raw(data, page=page)

    def push_text(self, text: str, page: Optional[int] = None,
                  font_size: int = 48, align: str = "center") -> dict:
        """
        Render and push text.

        Args:
            text: Text to display (supports newlines)
            page: Page to store (0-3), or None to display immediately
            font_size: Font size in pixels
            align: Text alignment ("left", "center", "right")
        """
        data = text_to_raw(text, font_size=font_size, align=align)
        return self.push_raw(data, page=page)


def image_to_raw(image_path: str, invert: bool = False, dither: bool = True) -> bytes:
    """
    Convert image file to raw 1-bit bitmap.

    Args:
        image_path: Path to image file
        invert: Invert black/white
        dither: Use Floyd-Steinberg dithering

    Returns:
        Raw bitmap data (48000 bytes)
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow required: pip install Pillow")

    img = Image.open(image_path)
    img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    img = img.convert("L")  # Grayscale

    if dither:
        img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        img = img.point(lambda x: 255 if x > 127 else 0, mode="1")

    if invert:
        img = Image.eval(img, lambda x: 255 - x)

    # Convert to raw bytes (MSB first)
    data = bytearray(IMAGE_BYTES)
    pixels = img.load()

    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_idx = (y * WIDTH + x) // 8
            bit_idx = 7 - (x % 8)
            if pixels[x, y]:  # White pixel
                data[byte_idx] |= (1 << bit_idx)

    return bytes(data)


def text_to_raw(text: str, font_size: int = 48, align: str = "center",
                font_path: Optional[str] = None) -> bytes:
    """
    Render text to raw 1-bit bitmap.

    Args:
        text: Text to render (supports newlines)
        font_size: Font size in pixels
        align: Text alignment ("left", "center", "right")
        font_path: Path to TTF font file (uses default if None)

    Returns:
        Raw bitmap data (48000 bytes)
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ImportError("Pillow required: pip install Pillow")

    img = Image.new("1", (WIDTH, HEIGHT), color=1)  # White background
    draw = ImageDraw.Draw(img)

    # Load font
    if font_path:
        font = ImageFont.truetype(font_path, font_size)
    else:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", font_size)
        except OSError:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size)
            except OSError:
                font = ImageFont.load_default()

    # Calculate text position
    lines = text.split("\n")
    line_height = font_size + 10
    total_height = len(lines) * line_height
    y_start = (HEIGHT - total_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]

        if align == "center":
            x = (WIDTH - text_width) // 2
        elif align == "right":
            x = WIDTH - text_width - 20
        else:
            x = 20

        y = y_start + i * line_height
        draw.text((x, y), line, font=font, fill=0)  # Black text

    # Convert to raw bytes
    data = bytearray(IMAGE_BYTES)
    pixels = img.load()

    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_idx = (y * WIDTH + x) // 8
            bit_idx = 7 - (x % 8)
            if pixels[x, y]:  # White pixel
                data[byte_idx] |= (1 << bit_idx)

    return bytes(data)


def create_pattern(pattern: str = "checkerboard") -> bytes:
    """
    Create a test pattern.

    Args:
        pattern: Pattern type ("checkerboard", "horizontal", "vertical", "diagonal")

    Returns:
        Raw bitmap data (48000 bytes)
    """
    data = bytearray(IMAGE_BYTES)

    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_idx = (y * WIDTH + x) // 8
            bit_idx = 7 - (x % 8)
            pixel_white = False

            if pattern == "checkerboard":
                pixel_white = ((x // 48) + (y // 48)) % 2 == 0
            elif pattern == "horizontal":
                pixel_white = (y // 32) % 2 == 0
            elif pattern == "vertical":
                pixel_white = (x // 32) % 2 == 0
            elif pattern == "diagonal":
                pixel_white = ((x + y) // 16) % 2 == 0

            if pixel_white:
                data[byte_idx] |= (1 << bit_idx)

    return bytes(data)


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="reTerminal E1001 Client")
    parser.add_argument("--host", required=True, help="Device IP address")
    parser.add_argument("--page", type=int, help="Page to store (0-3)")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="Text to display")
    group.add_argument("--image", help="Image file to display")
    group.add_argument("--pattern", choices=["checkerboard", "horizontal", "vertical", "diagonal"],
                       help="Test pattern")
    group.add_argument("--status", action="store_true", help="Get device status")
    group.add_argument("--beep", action="store_true", help="Trigger buzzer")
    group.add_argument("--next", action="store_true", help="Next page")
    group.add_argument("--prev", action="store_true", help="Previous page")

    parser.add_argument("--font-size", type=int, default=48, help="Font size for text")
    parser.add_argument("--invert", action="store_true", help="Invert colors")

    args = parser.parse_args()

    rt = ReTerminal(args.host)

    if args.status:
        import json
        print(json.dumps(rt.status(), indent=2))
    elif args.beep:
        rt.beep()
        print("Beeped!")
    elif args.next:
        result = rt.next_page()
        print(f"Page: {result['page']} ({result['name']})")
    elif args.prev:
        result = rt.prev_page()
        print(f"Page: {result['page']} ({result['name']})")
    elif args.text:
        result = rt.push_text(args.text, page=args.page, font_size=args.font_size)
        print(f"Pushed text: {result}")
    elif args.image:
        result = rt.push_image(args.image, page=args.page, invert=args.invert)
        print(f"Pushed image: {result}")
    elif args.pattern:
        data = create_pattern(args.pattern)
        result = rt.push_raw(data, page=args.page)
        print(f"Pushed pattern: {result}")
