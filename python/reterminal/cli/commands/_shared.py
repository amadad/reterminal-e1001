"""Option defaults and helpers shared across CLI command modules."""

from __future__ import annotations

import json

import typer

HostOption = typer.Option(None, "--host", "-h", help="Device IP address")
PageOption = typer.Option(None, "--page", help="Device slot to store/show")


def emit_output(payload: object, output: str = "table") -> bool:
    """Emit a JSON payload when requested and report whether we handled output."""
    if output == "json":
        typer.echo(json.dumps(payload, indent=2, default=str))
        return True
    return False


def require_live_action(action: str, *, live: bool, non_interactive: bool) -> None:
    """Require an explicit opt-in before mutating the live device."""
    if not live:
        typer.echo(
            f"Error: {action} mutates the live device. "
            "Use --live to confirm or choose a preview/read-only command instead."
        )
        raise typer.Exit(1)
    if non_interactive:
        typer.echo(f"Error: --non-interactive cannot be combined with live action '{action}'.")
        raise typer.Exit(1)
