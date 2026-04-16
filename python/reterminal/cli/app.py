"""Main Typer CLI application."""

import sys

import typer
from loguru import logger

from reterminal.config import settings
from reterminal.version import __version__

# Configure loguru
logger.remove()  # Remove default handler
logger.add(
    sys.stderr,
    level=settings.log_level,
    format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
)

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


def version_callback(value: bool):
    if value:
        typer.echo(f"reterminal {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
    _show_version: bool = typer.Option(False, "--version", "-V", callback=version_callback, is_eager=True, help="Show version"),
):
    """reTerminal E1001 CLI - control your ePaper display."""
    if verbose:
        logger.remove()
        logger.add(
            sys.stderr,
            level="DEBUG",
            format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        )


# Import commands to register them
from reterminal.cli import commands  # noqa: F401, E402
