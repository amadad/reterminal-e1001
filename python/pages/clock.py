#!/usr/bin/env python3
"""
Display current time on reTerminal.

Usage:
    python clock.py --host 192.168.1.100 --page 1

    # Run continuously, updating every minute
    python clock.py --host 192.168.1.100 --page 1 --loop
"""

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from reterminal import ReTerminal

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Display clock on reTerminal")
    parser.add_argument("--host", required=True, help="Device IP")
    parser.add_argument("--page", type=int, help="Page to store (0-3)")
    parser.add_argument("--loop", action="store_true", help="Update continuously")
    args = parser.parse_args()

    rt = ReTerminal(args.host)

    while True:
        now = datetime.now()
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%A\n%B %d, %Y")

        text = f"{time_str}\n\n{date_str}"

        try:
            rt.push_text(text, page=args.page, font_size=72)
            print(f"Updated: {now.strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"Error: {e}")

        if not args.loop:
            break

        # Wait until next minute
        time.sleep(60 - now.second)


if __name__ == "__main__":
    main()
