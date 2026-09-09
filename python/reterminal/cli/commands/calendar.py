"""Read-only Google Calendar acquisition into a local display source."""

import json
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

import typer

from reterminal.cli._typer_app import app
from reterminal.family.calendar_export import export_calendar


@app.command("calendar-export")
def calendar_export(
    destination: Path = typer.Option(..., "--destination", help="Local JSON source to replace atomically"),
    config_dir: Path = typer.Option(..., "--config-dir", help="Explicit gws account configuration directory"),
    calendar: str = typer.Option("Family", help="Exact calendar name or calendar ID"),
    days: int = typer.Option(21, min=1, max=366, help="Calendar days including all of today"),
    timezone: str = typer.Option("America/New_York", help="Display timezone"),
    gws: str = typer.Option("gws", help="Installed gws executable"),
):
    """Read a complete calendar window; retain the previous file on upstream failure."""
    try:
        payload = export_calendar(destination, config_dir=config_dir, calendar=calendar,
                                  days=days, timezone=timezone, gws=gws)
    except (OSError, ValueError, TypeError, ZoneInfoNotFoundError, subprocess.SubprocessError) as exc:
        # Do not dump subprocess stdout/stderr; these can include private source data.
        typer.echo(f"Calendar export failed ({type(exc).__name__}); previous source retained.", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({"destination": str(destination.expanduser()),
                          "checked_at": payload["checked_at"], "events": len(payload["events"])}))
