#!/usr/bin/env python3
"""
Orchestrator for reTerminal page updates.

Usage:
    python refresh.py --host 192.168.7.77                    # Refresh all pages
    python refresh.py --host 192.168.7.77 --page market      # Refresh specific page
    python refresh.py --host 192.168.7.77 --page market,clock # Multiple pages
    python refresh.py --host 192.168.7.77 --list             # List available pages
"""

import argparse
import importlib.util
import sys
from pathlib import Path

# Default device IP
DEFAULT_HOST = "192.168.7.77"

# Page configuration: name -> (script, page_number)
PAGES = {
    "market": ("pages/market.py", 0),
    "clock": ("pages/clock.py", 1),
    "github": ("pages/github.py", 2),
    "status": ("pages/status.py", 3),
}

# Aliases
ALIASES = {
    "all": list(PAGES.keys()),
    "dashboard": ["market"],
}


def load_page_module(script_path: Path):
    """Dynamically load a page module."""
    spec = importlib.util.spec_from_file_location("page", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["page"] = module
    spec.loader.exec_module(module)
    return module


def refresh_page(name: str, host: str):
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

    # Run the page script
    import subprocess
    result = subprocess.run(
        [sys.executable, str(script_path), "--host", host, "--page", str(page_num)],
        cwd=Path(__file__).parent,
        capture_output=False
    )

    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Orchestrator for reTerminal page updates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python refresh.py                          # Refresh all (uses default host)
    python refresh.py --page market            # Just market page
    python refresh.py --page market,clock      # Market and clock
    python refresh.py --list                   # Show available pages
        """
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Device IP (default: {DEFAULT_HOST})")
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

    # Determine which pages to refresh
    if args.page:
        page_names = args.page.split(",")
        # Expand aliases
        expanded = []
        for name in page_names:
            name = name.strip().lower()
            if name in ALIASES:
                expanded.extend(ALIASES[name])
            else:
                expanded.append(name)
        page_names = expanded
    else:
        # Default: refresh all
        page_names = list(PAGES.keys())

    print(f"Refreshing pages: {', '.join(page_names)}")
    print(f"Device: {args.host}")

    # Refresh each page
    success = 0
    for name in page_names:
        if refresh_page(name, args.host):
            success += 1

    print(f"\n=== Done: {success}/{len(page_names)} pages refreshed ===")


if __name__ == "__main__":
    main()
