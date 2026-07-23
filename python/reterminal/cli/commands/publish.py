"""Publish-pipeline commands: publish, lint, brief."""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from reterminal.app import DisplayPublisher, PublishResult
from reterminal.cli._typer_app import app
from reterminal.cli.commands._shared import HostOption, emit_output, require_live_action
from reterminal.device import ReTerminalDevice
from reterminal.providers import build_scene_providers, build_providers, is_manifest_shape, load_manifest
from reterminal.render import MonoRenderer
from reterminal.scheduler import PriorityScheduler


def build_publish_payload(result: PublishResult, target_host: str | None = None) -> dict[str, object]:
    """Build a machine-readable publish summary."""
    assignments = []
    for slot, assignment in sorted(result.assignments.items()):
        entry = {
            "slot": slot,
            "scene_id": assignment.scene.id,
            "scene_kind": assignment.scene.kind,
            "priority": assignment.scene.priority,
        }
        push_result = result.push_results.get(slot)
        if push_result is not None:
            entry["push_result"] = push_result
        assignments.append(entry)

    return {
        "slot_count": result.slot_count,
        "scene_count": len(result.scenes),
        "assignments": assignments,
        "preview_paths": [str(path) for path in result.preview_paths],
        "shown_slot": result.shown_slot,
        "target_host": target_host,
    }


def next_assigned_slot(current_slot: int | None, assigned_slots: list[int]) -> int | None:
    """Rotate to the next assigned slot, wrapping back to the first slot."""
    if not assigned_slots:
        return None
    if current_slot not in assigned_slots:
        return assigned_slots[0]
    current_index = assigned_slots.index(current_slot)
    return assigned_slots[(current_index + 1) % len(assigned_slots)]


def print_publish_result(result: PublishResult, target_host: str | None = None) -> None:
    """Render a consistent publish summary for one run."""
    typer.echo(f"Selected {len(result.assignments)} scene(s) for {result.slot_count} slot(s):")
    for slot, assignment in sorted(result.assignments.items()):
        line = (
            f"  slot {slot}: {assignment.scene.id} "
            f"[{assignment.scene.kind}] priority={assignment.scene.priority}"
        )
        push_result = result.push_results.get(slot)
        if push_result and push_result.get("skipped"):
            line += " (unchanged, upload skipped)"
        typer.echo(line)

    if result.preview_paths:
        typer.echo("\nPreview files:")
        for path in result.preview_paths:
            typer.echo(f"  {path}")

    if target_host is not None:
        typer.echo(f"\nPushed {len(result.assignments)} scene(s) to {target_host}")
        if result.shown_slot is not None:
            typer.echo(f"Visible slot: {result.shown_slot}")


@app.command()
def publish(
    feed: Optional[Path] = typer.Option(None, "--feed", "-f", help="Path to scene feed JSON"),
    paperclip_url: Optional[str] = typer.Option(None, "--paperclip-url", help="Remote Paperclip-compatible scene feed URL"),
    host: Optional[str] = HostOption,
    preview: Optional[Path] = typer.Option(None, "--preview", help="Directory for rendered previews"),
    push: bool = typer.Option(False, "--push", help="Push rendered scenes to the device"),
    include_system: bool = typer.Option(False, "--include-system/--no-include-system", help="Include a built-in ambient system scene"),
    slot_count: Optional[int] = typer.Option(None, "--slots", min=1, help="Override physical slot count"),
    show_slot: Optional[int] = typer.Option(None, "--show-slot", min=0, help="Select a visible slot after pushing; omitted preserves the current visible slot"),
    interval: Optional[int] = typer.Option(None, "--interval", min=1, help="Repeat publish every N seconds"),
    watch: bool = typer.Option(False, "--watch", help="FSEvents-driven loop (requires --feed pointing at a manifest); replaces --interval"),
    live: bool = typer.Option(False, "--live", help="Confirm a live device mutation"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Fail instead of mutating the live device"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Render logical scenes, schedule them into hardware slots, and preview/push them."""
    manifest_feed = False
    if feed is not None and feed.exists():
        try:
            data = json.loads(feed.read_text())
            manifest_feed = is_manifest_shape(data)
        except (json.JSONDecodeError, OSError):
            manifest_feed = False

    if watch:
        if not manifest_feed or feed is None:
            typer.echo("Error: --watch requires --feed pointing at a provider manifest")
            raise typer.Exit(1)
        if show_slot is not None:
            typer.echo("Error: --show-slot is not supported with --watch; watch preserves the current visible slot")
            raise typer.Exit(1)
        if include_system:
            typer.echo("Error: --include-system is not supported with --watch; add providers to the manifest")
            raise typer.Exit(1)
        if push:
            typer.echo("Error: --push is not supported with --watch; the device pulls on wake")
            raise typer.Exit(1)
        if host is not None:
            typer.echo("Error: --host is not supported with --watch; the device knows the publisher host")
            raise typer.Exit(1)
        if not live:
            typer.echo("Error: --watch serves content on the LAN. Use --live to confirm.")
            raise typer.Exit(1)

        from reterminal.app.live import run_live

        run_live(feed)
        return

    if show_slot is not None and not push:
        typer.echo("Error: --show-slot requires --push")
        raise typer.Exit(1)
    if push:
        require_live_action("publish --push", live=live, non_interactive=non_interactive)

    if manifest_feed:
        providers = build_providers(load_manifest(feed))
        if include_system:
            from reterminal.providers.system import SystemSceneProvider
            providers.append(SystemSceneProvider())
    else:
        providers = build_scene_providers(
            feed=feed,
            paperclip_url=paperclip_url,
            include_system=include_system,
        )

    if not providers:
        typer.echo("Error: provide --feed, --paperclip-url, or enable --include-system")
        raise typer.Exit(1)

    example_feed_warning = None
    if feed is not None and "examples" in feed.resolve().parts and not manifest_feed:
        example_feed_warning = "example feeds are static demo content and will not update on their own"
        if output != "json":
            typer.echo("Note: example feeds are static demo content and will not update on their own.")

    try:
        device = ReTerminalDevice(host) if push or host else None
        publisher = DisplayPublisher(
            providers=providers,
            renderer=MonoRenderer(),
            scheduler=PriorityScheduler(),
            device=device,
        )

        current_show_slot = show_slot
        cycle = 0
        while True:
            cycle += 1
            if interval is not None and output != "json":
                typer.echo(f"\n[{datetime.now().strftime('%H:%M:%S')}] Publish cycle {cycle}")

            result = publisher.publish(
                preview_dir=preview,
                push=push,
                slot_count=slot_count,
                show_slot=current_show_slot,
            )
            target_host = device.discover_capabilities().host if push and device else None
            payload = build_publish_payload(result, target_host=target_host)
            payload.update({
                "mode": "live" if push else "preview",
                "cycle": cycle,
                "example_feed_warning": example_feed_warning,
            })
            if not emit_output(payload, output):
                print_publish_result(result, target_host=target_host)

            if interval is None:
                break

            if push and show_slot is None:
                current_show_slot = next_assigned_slot(result.shown_slot, sorted(result.assignments))

            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("\nStopped publishing.")
    except Exception as e:
        logger.error(f"Failed to publish scenes: {e}")
        raise typer.Exit(1)


@app.command()
def lint(
    feed: Path = typer.Option(..., "--feed", "-f", exists=True, dir_okay=False, help="Provider manifest JSON to lint"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Validate every supported markdown source in a provider manifest.

    Walks each lintable file referenced by the manifest, runs the per-provider lint
    rules (same regexes the parsers use), and reports lines that would be
    silently dropped by the renderer. Exits non-zero if any issues are found.
    """
    from reterminal.providers.lint import lint_manifest_files, manifest_lint_specs

    manifest = load_manifest(feed)
    specs = manifest_lint_specs(manifest)
    issues = lint_manifest_files(specs)

    if output == "json":
        emit_output(
            {
                "feed": str(feed),
                "issues": [issue.to_dict() for issue in issues],
                "ok": not issues,
            },
            "json",
        )
    else:
        if not issues:
            typer.echo(f"OK: no lint issues across {len(specs)} source(s)")
        else:
            for issue in issues:
                typer.echo(f"{issue.file}:{issue.line}: {issue.reason}")
                if issue.raw:
                    typer.echo(f"    {issue.raw}")
    if issues:
        raise typer.Exit(1)


@app.command()
def brief(
    feed: Path = typer.Option(..., "--feed", "-f", exists=True, dir_okay=False, help="Provider manifest JSON to read family state from"),
    output: str = typer.Option("text", "--output", "-o", help="Output format: text, json"),
):
    """Print a morning summary built from the family-state files in a manifest.

    Sample non-display consumer of `reterminal.family`. Reads whatever
    calendar / missions / events / activities files the manifest names and
    folds them into a single daily readout — today's agenda, tomorrow's,
    each kid's next mission action, the closest upcoming event, and what's
    next in the activities queue. Useful as-is for a kitchen morning print
    or a Discord post; primarily a worked example for what other tools can
    do with the family API.
    """
    from reterminal.family import (
        Activity,
        CalendarItem,
        Event,
        Mission,
        events_for,
        parse_activities,
        parse_calendar,
        parse_events,
        parse_missions,
    )

    manifest = load_manifest(feed)
    paths_by_type: dict[str, Path] = {
        entry.type: p for entry in manifest.providers if (p := entry.path()) is not None
    }

    today: list[CalendarItem] = []
    tomorrow: list[CalendarItem] = []
    if (p := paths_by_type.get("calendar")) and p.exists():
        parsed = parse_calendar(p)
        today = events_for(parsed, date.today())
        tomorrow = events_for(parsed, date.today() + timedelta(days=1))

    missions: list[Mission] = []
    if (p := paths_by_type.get("missions")) and p.exists():
        missions = parse_missions(p)

    events: list[Event] = []
    if (p := paths_by_type.get("events")) and p.exists():
        events = parse_events(p)

    queue: list[Activity] = []
    if (p := paths_by_type.get("activities")) and p.exists():
        _recent, queue = parse_activities(p)

    if output == "json":
        payload = {
            "today": [
                {"time": i.time, "label": i.label, "who": i.who} for i in today
            ],
            "tomorrow": [
                {"time": i.time, "label": i.label, "who": i.who} for i in tomorrow
            ],
            "missions": [
                {"who": m.who, "kind": m.kind, "title": m.title, "next": m.next_action}
                for m in missions
            ],
            "next_event": (
                {
                    "label": events[0].label,
                    "on": events[0].on.isoformat(),
                    "days_until": events[0].days_until,
                    "tag": events[0].tag,
                }
                if events
                else None
            ),
            "watching_next": (
                {"label": queue[0].label, "tag": queue[0].tag} if queue else None
            ),
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    def _fmt_item(i: CalendarItem) -> str:
        who_str = f" ({i.who})" if i.who else ""
        return f"  {i.time or '—':>8}  {i.label}{who_str}"

    typer.echo("─" * 48)
    typer.echo("  Family brief")
    typer.echo("─" * 48)

    typer.echo(f"\nTODAY ({len(today)})")
    for i in today:
        typer.echo(_fmt_item(i))
    if not today:
        typer.echo("  (nothing scheduled)")

    typer.echo(f"\nTOMORROW ({len(tomorrow)})")
    for i in tomorrow:
        typer.echo(_fmt_item(i))
    if not tomorrow:
        typer.echo("  (nothing scheduled)")

    if missions:
        typer.echo("\nMISSIONS")
        for m in missions:
            label = m.title or "(no title)"
            nxt = m.next_action or "(no next)"
            typer.echo(f"  {m.who}: {label} → {nxt}")

    if events:
        next_ev = events[0]
        typer.echo("\nNEXT EVENT")
        typer.echo(f"  {next_ev.label} — in {next_ev.days_until} days ({next_ev.on:%b %d})")

    if queue:
        typer.echo("\nWATCHING NEXT")
        typer.echo(f"  {queue[0].label}")
