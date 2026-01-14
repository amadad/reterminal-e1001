#!/usr/bin/env python3
"""
Simple dashboard displaying system info.

Usage:
    python dashboard.py --host 192.168.1.100 --page 0
"""

import sys
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from reterminal import ReTerminal, text_to_raw, WIDTH, HEIGHT

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow required: pip install Pillow")
    sys.exit(1)


def get_system_info():
    """Gather system information."""
    info = {}

    # Hostname
    try:
        info["hostname"] = subprocess.check_output(["hostname"], text=True).strip()
    except:
        info["hostname"] = "unknown"

    # Uptime
    try:
        uptime = subprocess.check_output(["uptime"], text=True).strip()
        # Extract load average
        if "load average" in uptime:
            info["load"] = uptime.split("load average:")[-1].strip()
        else:
            info["load"] = "N/A"
    except:
        info["load"] = "N/A"

    # Time
    info["time"] = datetime.now().strftime("%H:%M")
    info["date"] = datetime.now().strftime("%Y-%m-%d")

    return info


def render_dashboard(info: dict) -> bytes:
    """Render dashboard to raw bitmap."""
    img = Image.new("1", (WIDTH, HEIGHT), color=1)  # White
    draw = ImageDraw.Draw(img)

    # Try to load fonts
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 72)
        font_medium = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 36)
        font_small = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 24)
    except OSError:
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large

    # Draw time (large, centered at top)
    time_bbox = draw.textbbox((0, 0), info["time"], font=font_large)
    time_width = time_bbox[2] - time_bbox[0]
    draw.text(((WIDTH - time_width) // 2, 60), info["time"], font=font_large, fill=0)

    # Draw date
    date_bbox = draw.textbbox((0, 0), info["date"], font=font_medium)
    date_width = date_bbox[2] - date_bbox[0]
    draw.text(((WIDTH - date_width) // 2, 160), info["date"], font=font_medium, fill=0)

    # Draw horizontal line
    draw.line([(50, 220), (WIDTH - 50, 220)], fill=0, width=2)

    # Draw hostname
    draw.text((50, 260), f"Host: {info['hostname']}", font=font_small, fill=0)

    # Draw load
    draw.text((50, 300), f"Load: {info['load']}", font=font_small, fill=0)

    # Convert to raw bytes
    from reterminal import IMAGE_BYTES
    data = bytearray(IMAGE_BYTES)
    pixels = img.load()

    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_idx = (y * WIDTH + x) // 8
            bit_idx = 7 - (x % 8)
            if pixels[x, y]:
                data[byte_idx] |= (1 << bit_idx)

    return bytes(data)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Display dashboard on reTerminal")
    parser.add_argument("--host", required=True, help="Device IP")
    parser.add_argument("--page", type=int, help="Page to store (0-3)")
    args = parser.parse_args()

    rt = ReTerminal(args.host)
    info = get_system_info()
    data = render_dashboard(info)

    result = rt.push_raw(data, page=args.page)
    print(f"Dashboard pushed: {result}")


if __name__ == "__main__":
    main()
