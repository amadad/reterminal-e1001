"""Main Typer CLI application."""

import sys

import typer
from loguru import logger

from reterminal import __version__
from reterminal.config import settings

# Configure loguru
logger.remove()  # Remove default handler
logger.add(
    sys.stderr,
    level=settings.log_level,
    format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
)

app = typer.Typer(
    name="reterminal",
    help="CLI for Seeed reTerminal E1001 ePaper display",
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
    version: bool = typer.Option(False, "--version", "-V", callback=version_callback, is_eager=True, help="Show version"),
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
