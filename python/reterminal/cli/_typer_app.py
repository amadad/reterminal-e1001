"""Shared Typer application instance for CLI subcommands.

This is a deliberately tiny leaf module: it constructs the ``app`` Typer
instance and nothing else. Both ``reterminal.cli.app`` (which wires the
top-level callback and registers subcommands by importing
``reterminal.cli.commands`` for side-effects) and ``reterminal.cli.commands``
(which decorates functions with ``@app.command``) import from here.

Splitting the ``app`` instance out of ``reterminal.cli.app`` removes the
``cli.app <-> cli.commands`` import cycle: both now depend on this leaf
instead of on each other.
"""

from __future__ import annotations

import typer

TOP_LEVEL_HELP = """CLI for Seeed reTerminal E1001 ePaper display.

Use when you need to discover a device, inspect capabilities, preview scene feeds,
or push content to the display with explicit `--live` approval.
"""

TOP_LEVEL_EPILOG = """Examples:
  reterminal discover --output json
  reterminal doctor --output json
  reterminal snapshot --png ./current.png --output json
  reterminal push --text \"hello\" --preview ./preview.png --output json
  reterminal publish --feed ./feed.json --preview ./previews --output json
  reterminal publish --feed ./feed.json --push --live
"""

app = typer.Typer(
    name="reterminal",
    help=TOP_LEVEL_HELP,
    epilog=TOP_LEVEL_EPILOG,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

__all__ = ["app", "TOP_LEVEL_HELP", "TOP_LEVEL_EPILOG"]
