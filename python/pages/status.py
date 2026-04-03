#!/usr/bin/env python3
"""
Display system/clawdbot status on reTerminal.

Usage:
    python status.py --host "$RETERMINAL_HOST" --page 3
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from reterminal import ReTerminal, WIDTH, HEIGHT, IMAGE_BYTES

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow required: pip install Pillow")
    sys.exit(1)


def get_status_data():
    """Get system and clawdbot status."""
    data = {
        "hostname": "unknown",
        "ip": "unknown",
        "clawdbot": "unknown",
        "telegram": "unknown",
        "uptime": "unknown"
    }

    try:
        # Hostname
        result = subprocess.run(["hostname"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            data["hostname"] = result.stdout.strip()

        # Get clawdbot health
        result = subprocess.run(
            ["clawdbot", "health"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            output = result.stdout
            if "Telegram: ok" in output:
                # Extract bot name
                for line in output.split("\n"):
                    if "Telegram:" in line and "@" in line:
                        data["telegram"] = line.split("(")[1].split(")")[0] if "(" in line else "connected"
                        break
                data["clawdbot"] = "running"
            else:
                data["clawdbot"] = "running"
        else:
            data["clawdbot"] = "stopped"

        # Uptime
        result = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            uptime = result.stdout.strip()
            # Extract just the uptime part
            if "up" in uptime:
                parts = uptime.split("up")[1].split(",")[0].strip()
                data["uptime"] = parts

    except Exception as e:
        print(f"Error getting status: {e}")

    return data


def render_status(data: dict, device_ip: str) -> bytes:
    """Render status to raw bitmap."""
    img = Image.new("1", (WIDTH, HEIGHT), color=1)  # White
    draw = ImageDraw.Draw(img)

    # Load fonts
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 36)
        font_large = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 48)
        font_medium = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 28)
        font_small = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 22)
    except OSError:
        font_title = font_large = font_medium = font_small = ImageFont.load_default()

    # Title
    draw.text((50, 30), "STATUS", font=font_title, fill=0)

    # Hostname
    draw.text((50, 90), data["hostname"], font=font_large, fill=0)

    # Divider
    draw.line([(50, 160), (WIDTH - 50, 160)], fill=0, width=2)

    # Status items
    y = 190
    draw.text((50, y), f"Clawdbot: {data['clawdbot']}", font=font_medium, fill=0)
    y += 50
    draw.text((50, y), f"Telegram: {data['telegram']}", font=font_medium, fill=0)
    y += 50
    draw.text((50, y), f"Uptime: {data['uptime']}", font=font_medium, fill=0)
    y += 50
    draw.text((50, y), f"Display: {device_ip}", font=font_medium, fill=0)

    # Timestamp
    now = datetime.now().strftime("%H:%M")
    draw.text((50, HEIGHT - 50), f"Updated: {now}", font=font_small, fill=0)

    # Convert to raw bytes (1 = black in GxEPD2)
    raw = bytearray(IMAGE_BYTES)
    pixels = img.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_idx = (y * WIDTH + x) // 8
            bit_idx = 7 - (x % 8)
            if not pixels[x, y]:
                raw[byte_idx] |= (1 << bit_idx)

    return bytes(raw)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Display status on reTerminal")
    parser.add_argument("--host", required=True, help="Device IP")
    parser.add_argument("--page", type=int, help="Device slot to store")
    args = parser.parse_args()

    print("Fetching status...")
    data = get_status_data()

    print(f"Host: {data['hostname']}")
    print(f"Clawdbot: {data['clawdbot']}")
    print(f"Telegram: {data['telegram']}")

    rt = ReTerminal(args.host)
    raw = render_status(data, args.host)
    result = rt.push_raw(raw, page=args.page)
    print(f"Status page pushed: {result}")


if __name__ == "__main__":
    main()
