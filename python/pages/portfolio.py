#!/usr/bin/env python3
"""
Display portfolio summary on reTerminal.

Reads from schwab-cli-tools portfolio snapshots.

Usage:
    python portfolio.py --host 192.168.7.77 --page 0
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from reterminal import ReTerminal, WIDTH, HEIGHT, IMAGE_BYTES

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow required: pip install Pillow")
    sys.exit(1)

SNAPSHOT_DIR = Path.home() / "base/projects/schwab-cli-tools/private/snapshots"


def get_latest_snapshot():
    """Get the most recent portfolio snapshot."""
    snapshots = sorted(SNAPSHOT_DIR.glob("*.json"), reverse=True)
    if not snapshots:
        return None

    with open(snapshots[0]) as f:
        return json.load(f)


def format_currency(value):
    """Format number as currency."""
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value/1_000:.1f}K"
    else:
        return f"${value:.0f}"


def render_portfolio(data: dict) -> bytes:
    """Render portfolio summary to raw bitmap."""
    img = Image.new("1", (WIDTH, HEIGHT), color=1)  # White
    draw = ImageDraw.Draw(img)

    # Load fonts
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 48)
        font_large = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 72)
        font_medium = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 32)
        font_small = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 24)
    except OSError:
        font_title = font_large = font_medium = font_small = ImageFont.load_default()

    summary = data.get("summary", {})
    total = summary.get("total_value", 0)
    cash = summary.get("total_cash", 0)
    invested = summary.get("total_invested", 0)
    accounts = summary.get("api_account_count", 0)
    positions = summary.get("position_count", 0)
    snapshot_date = data.get("date", "Unknown")

    # Title
    draw.text((50, 30), "PORTFOLIO", font=font_title, fill=0)

    # Total value (large)
    total_str = format_currency(total)
    bbox = draw.textbbox((0, 0), total_str, font=font_large)
    total_width = bbox[2] - bbox[0]
    draw.text(((WIDTH - total_width) // 2, 100), total_str, font=font_large, fill=0)

    # Divider
    draw.line([(50, 200), (WIDTH - 50, 200)], fill=0, width=2)

    # Details
    y = 230
    draw.text((50, y), f"Cash:     {format_currency(cash)}", font=font_medium, fill=0)
    y += 50
    draw.text((50, y), f"Invested: {format_currency(invested)}", font=font_medium, fill=0)
    y += 50
    draw.text((50, y), f"Accounts: {accounts}  |  Positions: {positions}", font=font_small, fill=0)

    # Date at bottom
    draw.text((50, HEIGHT - 50), f"Updated: {snapshot_date}", font=font_small, fill=0)

    # Convert to raw bytes (1 = black in GxEPD2)
    raw = bytearray(IMAGE_BYTES)
    pixels = img.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_idx = (y * WIDTH + x) // 8
            bit_idx = 7 - (x % 8)
            if not pixels[x, y]:  # Black pixel = set bit
                raw[byte_idx] |= (1 << bit_idx)

    return bytes(raw)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Display portfolio on reTerminal")
    parser.add_argument("--host", required=True, help="Device IP")
    parser.add_argument("--page", type=int, help="Page to store (0-3)")
    args = parser.parse_args()

    data = get_latest_snapshot()
    if not data:
        print("No portfolio snapshot found")
        sys.exit(1)

    rt = ReTerminal(args.host)
    raw = render_portfolio(data)
    result = rt.push_raw(raw, page=args.page)

    print(f"Portfolio pushed: {result}")
    print(f"Total: {format_currency(data['summary']['total_value'])}")


if __name__ == "__main__":
    main()
