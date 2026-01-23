"""Pixel encoding utilities for ePaper display.

This is the single source of truth for converting images to raw bitmap format.
The reTerminal E1001 uses GxEPD2 which draws 1-bits as BLACK pixels.

Display specs:
- Resolution: 800x480 pixels
- Format: 1-bit monochrome, MSB first
- Size: 48000 bytes (800 * 480 / 8)
- Encoding: 1 = black pixel, 0 = white pixel
"""

from pathlib import Path
from typing import Union

from PIL import Image

from reterminal.config import WIDTH, HEIGHT, IMAGE_BYTES
from reterminal.exceptions import ImageError


def pil_to_raw(img: Image.Image) -> bytes:
    """
    Convert PIL Image to raw 1-bit bitmap for ePaper display.

    Args:
        img: PIL Image (will be converted to 1-bit if needed)

    Returns:
        Raw bitmap data (48000 bytes)

    Note:
        GxEPD2 draws 1-bits as BLACK. This function sets bit=1 for dark pixels.
    """
    # Ensure correct dimensions
    if img.size != (WIDTH, HEIGHT):
        img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

    # Convert to 1-bit if needed
    if img.mode != "1":
        img = img.convert("L").convert("1", dither=Image.Dither.FLOYDSTEINBERG)

    # Convert to raw bytes (MSB first)
    raw = bytearray(IMAGE_BYTES)
    pixels = img.load()

    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_idx = (y * WIDTH + x) // 8
            bit_idx = 7 - (x % 8)
            # Black pixel (0 in PIL mode="1") = set bit to 1
            if not pixels[x, y]:
                raw[byte_idx] |= (1 << bit_idx)

    return bytes(raw)


def image_to_raw(
    image_path: Union[str, Path],
    invert: bool = False,
    dither: bool = True,
) -> bytes:
    """
    Load image file and convert to raw 1-bit bitmap.

    Args:
        image_path: Path to image file (PNG, JPG, etc.)
        invert: Invert black/white
        dither: Use Floyd-Steinberg dithering (default True)

    Returns:
        Raw bitmap data (48000 bytes)
    """
    path = Path(image_path)
    if not path.exists():
        raise ImageError(f"Image file not found: {path}")

    try:
        img = Image.open(path)
    except Exception as e:
        raise ImageError(f"Failed to open image: {e}")

    # Resize to display dimensions
    img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

    # Convert to grayscale
    img = img.convert("L")

    # Apply dithering or threshold
    if dither:
        img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        img = img.point(lambda x: 255 if x > 127 else 0, mode="1")

    # Invert if requested
    if invert:
        img = Image.eval(img, lambda x: 255 - x)

    return pil_to_raw(img)


def text_to_raw(
    text: str,
    font_size: int = 48,
    align: str = "center",
    font_path: str = None,
) -> bytes:
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
    from PIL import ImageDraw, ImageFont
    from reterminal.fonts import load_font

    img = Image.new("1", (WIDTH, HEIGHT), color=1)  # White background
    draw = ImageDraw.Draw(img)

    # Load font
    font = load_font(font_path, font_size) if font_path else load_font(size=font_size)

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

    return pil_to_raw(img)


def create_pattern(pattern: str = "checkerboard") -> bytes:
    """
    Create a test pattern.

    Args:
        pattern: Pattern type ("checkerboard", "horizontal", "vertical", "diagonal")

    Returns:
        Raw bitmap data (48000 bytes)
    """
    raw = bytearray(IMAGE_BYTES)

    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_idx = (y * WIDTH + x) // 8
            bit_idx = 7 - (x % 8)
            pixel_black = False

            if pattern == "checkerboard":
                pixel_black = ((x // 48) + (y // 48)) % 2 == 1
            elif pattern == "horizontal":
                pixel_black = (y // 32) % 2 == 1
            elif pattern == "vertical":
                pixel_black = (x // 32) % 2 == 1
            elif pattern == "diagonal":
                pixel_black = ((x + y) // 16) % 2 == 1

            if pixel_black:
                raw[byte_idx] |= (1 << bit_idx)

    return bytes(raw)
