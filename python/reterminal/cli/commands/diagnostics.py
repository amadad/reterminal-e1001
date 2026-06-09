"""Configuration and health commands: config, discover, doctor, probe."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from reterminal.cli._typer_app import app
from reterminal.cli.commands._shared import HostOption, emit_output, require_live_action
from reterminal.config import settings
from reterminal.diagnostics import build_discovery_candidates, discover_hosts, run_doctor
from reterminal.probe import VALID_PATTERNS, format_report, run_probe
from reterminal.providers import is_manifest_shape, load_manifest


@app.command()
def config(
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Show current configuration."""
    payload = {
        "host": settings.host or None,
        "timeout": settings.timeout,
        "log_level": settings.log_level,
        "retry_attempts": settings.retry_attempts,
        "retry_min_wait": settings.retry_min_wait,
        "retry_max_wait": settings.retry_max_wait,
    }
    if emit_output(payload, output):
        return

    typer.echo(f"{'─' * 40}")
    typer.echo("  reTerminal Configuration")
    typer.echo(f"{'─' * 40}")
    typer.echo(f"  {'Host':20} {settings.host or '<unset>'}")
    typer.echo(f"  {'Timeout':20} {settings.timeout}s")
    typer.echo(f"  {'Log Level':20} {settings.log_level}")
    typer.echo(f"  {'Retry Attempts':20} {settings.retry_attempts}")
    typer.echo(f"  {'Retry Wait':20} {settings.retry_min_wait}-{settings.retry_max_wait}s")
    typer.echo(f"{'─' * 40}")
    typer.echo("\nSet via environment variables (RETERMINAL_*) or .env file")


@app.command()
def discover(
    host: Optional[str] = HostOption,
    candidate: list[str] = typer.Option(None, "--candidate", help="Additional host/IP candidate to probe"),
    subnet: Optional[str] = typer.Option(None, "--subnet", help="Subnet prefix to scan, e.g. 192.168.1"),
    start: int = typer.Option(1, "--start", min=0, max=255, help="Start of subnet scan range"),
    end: int = typer.Option(254, "--end", min=0, max=255, help="End of subnet scan range"),
    timeout: float = typer.Option(1.5, "--timeout", min=0.1, help="Per-host timeout in seconds"),
    workers: int = typer.Option(16, "--workers", min=1, help="Parallel probes to run"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Discover reachable reTerminal hosts by probing common names and optional IP ranges."""
    try:
        configured_host = host or settings.host or None
        candidates = build_discovery_candidates(
            configured_host,
            candidates=list(candidate or []),
            subnet=subnet,
            start=start,
            end=end,
        )
        results = discover_hosts(candidates, timeout=timeout, workers=workers)

        if output == "json":
            payload = [
                {
                    "target": result.target,
                    "reachable": result.reachable,
                    "status": result.status,
                    "page_info": result.page_info,
                    "error": result.error,
                    "latency_ms": result.latency_ms,
                }
                for result in results
            ]
            typer.echo(json.dumps(payload, indent=2))
            return

        if not results:
            typer.echo("No reachable reTerminal hosts found.")
            if subnet is None:
                typer.echo("Tip: retry with --subnet 192.168.x if your device is on DHCP without mDNS.")
            return

        typer.echo(f"Found {len(results)} reachable device(s):")
        for result in results:
            status = result.status or {}
            page_info = result.page_info or {}
            typer.echo(
                f"  {result.target:20} ip={status.get('ip', '?')} "
                f"ssid={status.get('ssid', '?')} page={page_info.get('page', '?')}/{page_info.get('total', '?')} "
                f"latency={result.latency_ms}ms"
            )
    except Exception as e:
        logger.error(f"Failed to discover devices: {e}")
        raise typer.Exit(1)


def _lint_manifest_if_present(feed: Optional[Path]) -> list[dict[str, str | int]]:
    """Lint the markdown sources of a provider manifest, returning issues as dicts."""
    if feed is None or not feed.exists():
        return []
    try:
        data = json.loads(feed.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    if not is_manifest_shape(data):
        return []
    from reterminal.providers.lint import lint_manifest_files
    manifest = load_manifest(feed)
    specs: list[tuple[str, Path]] = [
        (entry.type, p) for entry in manifest.providers if (p := entry.path()) is not None
    ]
    return [issue.to_dict() for issue in lint_manifest_files(specs)]


@app.command()
def doctor(
    host: Optional[str] = HostOption,
    feed: Optional[Path] = typer.Option(None, "--feed", "-f", help="Optional scene feed JSON to validate"),
    paperclip_url: Optional[str] = typer.Option(None, "--paperclip-url", help="Optional Paperclip-compatible feed URL to validate"),
    include_system: bool = typer.Option(False, "--include-system/--no-include-system", help="Include the built-in system scene in the dry run"),
    skip_lint: bool = typer.Option(False, "--skip-lint", help="Skip linting markdown sources of the manifest"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Run operational checks for connectivity, slot truth, and publish-pipeline readiness.

    When `--feed` points at a provider manifest, also lints every markdown
    source it references (same checks as `reterminal lint`). Lint findings
    surface as warnings, not errors — bad authoring shows up here instead
    of silently disappearing from the rendered display.
    """
    try:
        report = run_doctor(
            host,
            feed=feed,
            paperclip_url=paperclip_url,
            include_system=include_system,
        )
        lint_issues = [] if skip_lint else _lint_manifest_if_present(feed)

        if output == "json":
            payload = {
                "configured_host": report.configured_host,
                "resolved_host": report.resolved_host,
                "reachable": report.reachable,
                "capabilities": report.capabilities.to_dict() if report.capabilities else None,
                "scene_count": report.scene_count,
                "assignment_count": report.assignment_count,
                "repo_build_sha": report.repo_build_sha,
                "firmware_match": report.firmware_match,
                "warnings": report.warnings,
                "errors": report.errors,
                "lint_issues": lint_issues,
            }
            typer.echo(json.dumps(payload, indent=2))
            if report.errors:
                raise typer.Exit(1)
            return

        typer.echo(f"{'─' * 48}")
        typer.echo("  reTerminal Doctor")
        typer.echo(f"{'─' * 48}")
        typer.echo(f"  {'Configured Host':20} {report.configured_host or '<unset>'}")
        typer.echo(f"  {'Reachable':20} {'yes' if report.reachable else 'no'}")
        if report.capabilities is not None:
            typer.echo(f"  {'Resolved Host':20} {report.capabilities.host}")
            typer.echo(f"  {'Page Slots':20} {report.capabilities.page_slots}")
            typer.echo(f"  {'Current Page':20} {report.capabilities.current_page}")
            if report.capabilities.firmware_version is not None:
                typer.echo(f"  {'Firmware':20} {report.capabilities.firmware_version}")
            if report.capabilities.build_sha is not None:
                typer.echo(f"  {'Build SHA':20} {report.capabilities.build_sha}")
            if report.repo_build_sha is not None:
                typer.echo(f"  {'Repo SHA':20} {report.repo_build_sha}")
            if report.firmware_match is not None:
                typer.echo(f"  {'Firmware Match':20} {report.firmware_match}")
            typer.echo(f"  {'Scene Count':20} {report.scene_count}")
            typer.echo(f"  {'Assignments':20} {report.assignment_count}")
        if lint_issues:
            typer.echo(f"\nLint ({len(lint_issues)} issue(s)):")
            for issue in lint_issues:
                typer.echo(f"  {issue['file']}:{issue['line']}: {issue['reason']}")
                if issue.get("raw"):
                    typer.echo(f"      {issue['raw']}")
        if report.warnings:
            typer.echo("\nWarnings:")
            for warning in report.warnings:
                typer.echo(f"  - {warning}")
        if report.errors:
            typer.echo("\nErrors:")
            for error in report.errors:
                typer.echo(f"  - {error}")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Failed to run doctor: {e}")
        raise typer.Exit(1)


@app.command()
def probe(
    host: Optional[str] = HostOption,
    upload_pages: bool = typer.Option(
        False,
        "--upload-pages",
        help="Destructively upload a test pattern into page slots",
    ),
    slots: int = typer.Option(8, "--slots", min=1, help="How many page slots to probe"),
    expected_pages: int = typer.Option(
        4,
        "--expected-pages",
        min=1,
        help="Expected host-side page count to compare against",
    ),
    pattern: str = typer.Option(
        "checkerboard",
        "--pattern",
        help=f"Probe pattern: {', '.join(VALID_PATTERNS)}",
    ),
    output: Optional[Path] = typer.Option(None, "--output", help="Write full JSON report to file"),
    live: bool = typer.Option(False, "--live", help="Confirm a destructive live device mutation"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Fail instead of mutating the live device"),
):
    """Probe device capabilities before refactoring architecture."""
    if upload_pages:
        require_live_action("probe --upload-pages", live=live, non_interactive=non_interactive)

    if pattern not in VALID_PATTERNS:
        typer.echo(f"Invalid pattern. Choose from: {', '.join(VALID_PATTERNS)}")
        raise typer.Exit(1)

    try:
        report = run_probe(
            host,
            expected_pages=expected_pages,
            requested_slots=slots,
            pattern=pattern,
            upload_pages=upload_pages,
        )
        typer.echo(format_report(report))

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report.to_dict(), indent=2))
            typer.echo(f"\nSaved report: {output}")
    except Exception as e:
        logger.error(f"Failed to probe device: {e}")
        raise typer.Exit(1)
