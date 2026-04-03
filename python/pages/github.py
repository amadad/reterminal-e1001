#!/usr/bin/env python3
"""
Display GitHub activity on reTerminal.

Usage:
    python github.py --host "$RETERMINAL_HOST" --page 2
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


def get_github_data():
    """Get GitHub stats via gh CLI."""
    data = {"user": "amadad", "repos": 0, "followers": 0, "recent": []}

    try:
        # Get user stats
        result = subprocess.run(
            ["gh", "api", "users/amadad", "--jq", "{public_repos, followers}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            import json
            stats = json.loads(result.stdout)
            data["repos"] = stats.get("public_repos", 0)
            data["followers"] = stats.get("followers", 0)

        # Get recent activity
        result = subprocess.run(
            ["gh", "api", "users/amadad/events", "--jq", '.[0:3] | .[] | "\(.type)|\(.repo.name)"'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if "|" in line:
                    event_type, repo = line.split("|", 1)
                    # Simplify event type
                    event_type = event_type.replace("Event", "")
                    # Shorten repo name
                    repo = repo.split("/")[-1] if "/" in repo else repo
                    data["recent"].append({"type": event_type, "repo": repo})
    except Exception as e:
        print(f"Error getting GitHub data: {e}")

    return data


def render_github(data: dict) -> bytes:
    """Render GitHub stats to raw bitmap."""
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
    draw.text((50, 30), "GITHUB", font=font_title, fill=0)

    # Username
    draw.text((50, 90), f"@{data['user']}", font=font_large, fill=0)

    # Stats
    draw.text((50, 170), f"{data['repos']} repos", font=font_medium, fill=0)
    draw.text((300, 170), f"{data['followers']} followers", font=font_medium, fill=0)

    # Divider
    draw.line([(50, 230), (WIDTH - 50, 230)], fill=0, width=2)

    # Recent activity
    draw.text((50, 250), "Recent Activity", font=font_medium, fill=0)

    y = 300
    for activity in data["recent"][:3]:
        draw.text((50, y), f"{activity['type']}: {activity['repo']}", font=font_small, fill=0)
        y += 40

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
    parser = argparse.ArgumentParser(description="Display GitHub on reTerminal")
    parser.add_argument("--host", required=True, help="Device IP")
    parser.add_argument("--page", type=int, help="Device slot to store")
    args = parser.parse_args()

    print("Fetching GitHub data...")
    data = get_github_data()

    print(f"User: @{data['user']}")
    print(f"Repos: {data['repos']}, Followers: {data['followers']}")

    rt = ReTerminal(args.host)
    raw = render_github(data)
    result = rt.push_raw(raw, page=args.page)
    print(f"GitHub page pushed: {result}")


if __name__ == "__main__":
    main()
