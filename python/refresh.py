#!/usr/bin/env python3
"""
Orchestrator for legacy reTerminal page updates.

Usage:
    export RETERMINAL_HOST=192.168.7.76
    python refresh.py --host "$RETERMINAL_HOST"               # Refresh all pages
    python refresh.py --host "$RETERMINAL_HOST" --page market # Refresh specific page
    python refresh.py --host "$RETERMINAL_HOST" --page market,clock
    python refresh.py --list
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_HOST = os.getenv("RETERMINAL_HOST", "")

# Page configuration: name -> (script, page_number)
PAGES = {
    "market": ("pages/market.py", 0),
    "clock": ("pages/clock.py", 1),
    "github": ("pages/github.py", 2),
    "status": ("pages/status.py", 3),
}

ALIASES = {
    "all": list(PAGES.keys()),
    "dashboard": ["market"],
}


def refresh_page(name: str, host: str) -> bool:
    """Refresh a single page."""
    if name not in PAGES:
        print(f"Unknown page: {name}")
        return False

    script, page_num = PAGES[name]
    script_path = Path(__file__).parent / script
    if not script_path.exists():
        print(f"Script not found: {script_path}")
        return False

    print(f"\n--- Refreshing {name} (page {page_num}) ---")
    result = subprocess.run(
        [sys.executable, str(script_path), "--host", host, "--page", str(page_num)],
        cwd=Path(__file__).parent,
        check=False,
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orchestrator for legacy reTerminal page updates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python refresh.py --host "$RETERMINAL_HOST"       # Refresh all
    python refresh.py --page market                    # Just market page
    python refresh.py --page market,clock              # Market and clock
    python refresh.py --list                           # Show available pages
        """,
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Device IP (or set RETERMINAL_HOST)")
    parser.add_argument("--page", help="Page(s) to refresh (comma-separated, or 'all')")
    parser.add_argument("--list", action="store_true", help="List available pages")
    args = parser.parse_args()

    if args.list:
        print("Available pages:")
        for name, (script, page_num) in PAGES.items():
            print(f"  {name:10} -> page {page_num} ({script})")
        print("\nAliases:")
        for alias, pages in ALIASES.items():
            print(f"  {alias:10} -> {', '.join(pages)}")
        return

    if not args.host:
        parser.error("Set RETERMINAL_HOST or pass --host with the device IP")

    if args.page:
        page_names = args.page.split(",")
        expanded = []
        for name in page_names:
            normalized = name.strip().lower()
            if normalized in ALIASES:
                expanded.extend(ALIASES[normalized])
            else:
                expanded.append(normalized)
        page_names = expanded
    else:
        page_names = list(PAGES.keys())

    print(f"Refreshing pages: {', '.join(page_names)}")
    print(f"Device: {args.host}")

    success = 0
    for name in page_names:
        if refresh_page(name, args.host):
            success += 1

    print(f"\n=== Done: {success}/{len(page_names)} pages refreshed ===")


if __name__ == "__main__":
    main()
