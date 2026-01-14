#!/usr/bin/env python3
"""
Display market pulse on reTerminal.

Shows VIX, S&P 500, Dow Jones from Schwab API.

Usage:
    python market.py --host 192.168.7.77 --page 0
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from reterminal import ReTerminal, WIDTH, HEIGHT, IMAGE_BYTES

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow required: pip install Pillow")
    sys.exit(1)


def get_market_data():
    """Get market data from Schwab via agent-alpha."""
    script = '''
from src.schwab_client import get_authenticated_client
import json

client = get_authenticated_client()
resp = client.get_quotes("$SPX,$DJI,$VIX")

if resp.status_code == 200:
    data = resp.json()
    result = {}
    for sym in ["$SPX", "$DJI", "$VIX"]:
        q = data.get(sym, {}).get("quote", {})
        result[sym] = {
            "price": q.get("lastPrice", q.get("closePrice", 0)),
            "change": q.get("netChange", 0),
            "pct": q.get("netPercentChange", 0)
        }
    print(json.dumps(result))
'''
    try:
        result = subprocess.run(
            ["uv", "run", "python", "-c", script],
            cwd=Path.home() / "Desktop/base/agent-alpha",
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            import json
            return json.loads(result.stdout.strip())
    except Exception as e:
        print(f"Error getting market data: {e}")
    return None


def render_market(data: dict) -> bytes:
    """Render market data to raw bitmap."""
    img = Image.new("1", (WIDTH, HEIGHT), color=1)  # White
    draw = ImageDraw.Draw(img)

    # Load fonts
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 36)
        font_large = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 56)
        font_medium = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 32)
        font_small = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 24)
    except OSError:
        font_title = font_large = font_medium = font_small = ImageFont.load_default()

    # Title
    draw.text((50, 30), "MARKET PULSE", font=font_title, fill=0)

    # Get VIX data
    vix = data.get("$VIX", {})
    vix_price = vix.get("price", 0)
    vix_pct = vix.get("pct", 0)

    # VIX interpretation
    if vix_price < 15:
        vix_mood = "LOW FEAR"
    elif vix_price < 20:
        vix_mood = "NORMAL"
    elif vix_price < 30:
        vix_mood = "ELEVATED"
    else:
        vix_mood = "HIGH FEAR"

    # VIX display (prominent)
    draw.text((50, 100), "VIX", font=font_medium, fill=0)
    draw.text((50, 140), f"{vix_price:.1f}", font=font_large, fill=0)
    draw.text((250, 160), f"{vix_pct:+.1f}%  {vix_mood}", font=font_medium, fill=0)

    # Divider
    draw.line([(50, 220), (WIDTH - 50, 220)], fill=0, width=2)

    # S&P 500
    spx = data.get("$SPX", {})
    y = 250
    draw.text((50, y), "S&P 500", font=font_medium, fill=0)
    draw.text((300, y), f"{spx.get('price', 0):,.0f}", font=font_medium, fill=0)
    draw.text((550, y), f"{spx.get('pct', 0):+.2f}%", font=font_medium, fill=0)

    # Dow Jones
    dji = data.get("$DJI", {})
    y = 310
    draw.text((50, y), "DOW", font=font_medium, fill=0)
    draw.text((300, y), f"{dji.get('price', 0):,.0f}", font=font_medium, fill=0)
    draw.text((550, y), f"{dji.get('pct', 0):+.2f}%", font=font_medium, fill=0)

    # Timestamp
    from datetime import datetime
    now = datetime.now().strftime("%H:%M")
    draw.text((50, HEIGHT - 50), f"Updated: {now}", font=font_small, fill=0)

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
    parser = argparse.ArgumentParser(description="Display market pulse on reTerminal")
    parser.add_argument("--host", required=True, help="Device IP")
    parser.add_argument("--page", type=int, help="Page to store (0-3)")
    args = parser.parse_args()

    print("Fetching market data...")
    data = get_market_data()

    if not data:
        print("Could not get market data")
        sys.exit(1)

    print(f"VIX: {data['$VIX']['price']:.1f} ({data['$VIX']['pct']:+.1f}%)")
    print(f"S&P: {data['$SPX']['price']:,.0f} ({data['$SPX']['pct']:+.2f}%)")
    print(f"DOW: {data['$DJI']['price']:,.0f} ({data['$DJI']['pct']:+.2f}%)")

    rt = ReTerminal(args.host)
    raw = render_market(data)
    result = rt.push_raw(raw, page=args.page)
    print(f"Market pulse pushed: {result}")


if __name__ == "__main__":
    main()
