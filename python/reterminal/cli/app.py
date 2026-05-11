"""Main Typer CLI application.

The ``app`` instance itself lives in :mod:`reterminal.cli._typer_app` so that
:mod:`reterminal.cli.commands` can import it without forming a circular
import back to this module.
"""

import sys

import typer
from loguru import logger

from reterminal.cli._typer_app import app
from reterminal.config import settings
from reterminal.version import __version__

logger.remove()
logger.add(
    sys.stderr,
    level=settings.log_level,
    format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
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


# Import subcommands for side-effect registration. This stays at module scope
# (rather than inside a function) so importing ``reterminal.cli.app`` is
# sufficient to register every command on ``app``.
from reterminal.cli import commands  # noqa: F401, E402  -- import for side-effect registration

__all__ = ["app", "main", "version_callback"]
