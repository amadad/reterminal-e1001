"""Option defaults and helpers shared across CLI command modules."""

from __future__ import annotations

import json
import os
from collections.abc import Callable

import typer
from loguru import logger

from reterminal.protocols import DisplayDevice
from reterminal.device import ReTerminalDevice
from reterminal.diagnostics import build_discovery_candidates, discover_hosts


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


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _discover_first_host(configured_host: str | None = None) -> str | None:
    subnet = os.getenv("RETERMINAL_DISCOVERY_SUBNET") or None
    candidates = build_discovery_candidates(configured_host, subnet=subnet)
    results = discover_hosts(
        candidates,
        timeout=_env_float("RETERMINAL_DISCOVERY_TIMEOUT", 1.5),
        workers=_env_int("RETERMINAL_DISCOVERY_WORKERS", 32),
    )
    if not results:
        return None
    first = results[0]
    return first.target or (first.status or {}).get("ip")


def _build_live_recover(device: ReTerminalDevice) -> Callable[[DisplayDevice], bool]:
    def recover(_device: DisplayDevice) -> bool:
        current_host = device.client.host
        discovered = _discover_first_host(current_host)
        if not discovered:
            # Demoted: this fires every retry while device is offline. The
            # live tracker logs the online/offline transition once.
            logger.debug("live: rediscovery found no reachable reTerminal host")
            return False
        if discovered != current_host:
            logger.info(f"live: rediscovered reTerminal at {discovered} (was {current_host})")
            device.connect_host(discovered)
        return True

    return recover
