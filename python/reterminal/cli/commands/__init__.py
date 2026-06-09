"""CLI commands for reterminal, grouped by domain.

Importing this package registers every command on the shared Typer ``app``
from :mod:`reterminal.cli._typer_app`:

- ``device`` — direct device operations (status, beep, buttons, page,
  clear, push, capabilities, snapshot)
- ``diagnostics`` — config, discover, doctor, probe
- ``publish`` — the publish pipeline plus lint and brief

``_shared`` holds the option defaults and helpers the command modules
have in common.
"""

from reterminal.cli.commands import device, diagnostics, publish  # noqa: F401  -- side-effect registration
from reterminal.cli.commands._shared import emit_output, require_live_action
from reterminal.cli.commands.publish import (
    build_publish_payload,
    next_assigned_slot,
    print_publish_result,
)

__all__ = [
    "build_publish_payload",
    "emit_output",
    "next_assigned_slot",
    "print_publish_result",
    "require_live_action",
]
