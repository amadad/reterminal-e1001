"""CLI commands for reterminal."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from reterminal.app import DisplayPublisher
from reterminal.cli.app import app
from reterminal.client import ReTerminal
from reterminal.config import settings, WIDTH, HEIGHT
from reterminal.device import ReTerminalDevice
from reterminal.diagnostics import build_discovery_candidates, discover_hosts, run_doctor
from reterminal.encoding import text_to_raw, image_to_raw, create_pattern, pil_to_raw
from reterminal.pages import get_page, list_pages, ALIASES
from reterminal.probe import VALID_PATTERNS, format_report, run_probe
from reterminal.providers import FileSceneProvider, PaperclipSceneProvider, SystemSceneProvider
from reterminal.render import MonoRenderer
from reterminal.scheduler import PriorityScheduler


# Common options
HostOption = typer.Option(None, "--host", "-h", help="Device IP address")
PageOption = typer.Option(None, "--page", help="Device slot to store/show")


def find_unsupported_legacy_pages(page_names: list[str], page_slots: int) -> list[tuple[str, int]]:
    """Return legacy pages whose fixed slot index exceeds the live device capacity."""
    unsupported: list[tuple[str, int]] = []
    for name in page_names:
        entry = get_page(name)
        if entry is None:
            continue
        _, default_page_num = entry
        if default_page_num >= page_slots:
            unsupported.append((name, default_page_num))
    return unsupported



def next_assigned_slot(current_slot: Optional[int], assigned_slots: list[int]) -> Optional[int]:
    """Rotate to the next assigned slot, wrapping back to the first slot."""
    if not assigned_slots:
        return None
    if current_slot not in assigned_slots:
        return assigned_slots[0]
    current_index = assigned_slots.index(current_slot)
    return assigned_slots[(current_index + 1) % len(assigned_slots)]



def warn_if_example_feed(feed: Optional[Path]) -> None:
    """Call out static example feeds so they are not mistaken for live data."""
    if feed is None:
        return
    resolved = feed.resolve()
    if "examples" in resolved.parts:
        typer.echo("Note: example feeds are static demo content and will not update on their own.")



def print_publish_result(result, target_host: Optional[str] = None) -> None:
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
def status(
    host: Optional[str] = HostOption,
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Get device status."""
    try:
        client = ReTerminal(host)
        result = client.status()
        if output == "json":
            typer.echo(json.dumps(result, indent=2))
        else:
            # Table output
            typer.echo(f"{'─' * 40}")
            typer.echo(f"  reTerminal Status ({client.host})")
            typer.echo(f"{'─' * 40}")
            for key, value in result.items():
                typer.echo(f"  {key:15} {value}")
            typer.echo(f"{'─' * 40}")
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise typer.Exit(1)


@app.command()
def beep(
    host: Optional[str] = HostOption,
    count: int = typer.Option(1, "--count", "-n", help="Number of beeps"),
    delay: float = typer.Option(0.3, "--delay", "-d", help="Delay between beeps"),
):
    """Trigger the buzzer."""
    try:
        client = ReTerminal(host)
        for i in range(count):
            client.beep()
            if i < count - 1:
                time.sleep(delay)
        typer.echo(f"Beeped {count}x!")
    except Exception as e:
        logger.error(f"Failed to beep: {e}")
        raise typer.Exit(1)


@app.command()
def buttons(
    host: Optional[str] = HostOption,
    watch: bool = typer.Option(False, "--watch", "-w", help="Watch button states continuously"),
):
    """Get button states."""
    try:
        client = ReTerminal(host)
        if watch:
            typer.echo("Watching buttons (Ctrl+C to stop)...")
            last_state = None
            while True:
                result = client.buttons()
                if result != last_state:
                    typer.echo(f"[{datetime.now().strftime('%H:%M:%S')}] {result}")
                    last_state = result
                time.sleep(0.1)
        else:
            result = client.buttons()
            typer.echo(json.dumps(result, indent=2))
    except KeyboardInterrupt:
        typer.echo("\nStopped watching.")
    except Exception as e:
        logger.error(f"Failed to get buttons: {e}")
        raise typer.Exit(1)


@app.command()
def page(
    action: Optional[str] = typer.Argument(None, help="Action: next, prev, or page number"),
    host: Optional[str] = HostOption,
):
    """Get or set current page. Use 'next', 'prev', or a page number."""
    try:
        client = ReTerminal(host)
        if action is None:
            result = client.get_page()
        elif action == "next":
            result = client.next_page()
        elif action == "prev":
            result = client.prev_page()
        else:
            try:
                page_num = int(action)
                result = client.set_page(page_num)
            except ValueError:
                typer.echo(f"Invalid action: {action}. Use 'next', 'prev', or a number.")
                raise typer.Exit(1)

        typer.echo(f"Page: {result.get('page', '?')} ({result.get('name', 'unknown')})")
    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Failed to manage page: {e}")
        raise typer.Exit(1)


@app.command()
def refresh(
    pages: Optional[str] = typer.Argument(None, help="Page(s) to refresh (comma-separated, or 'all')"),
    host: Optional[str] = HostOption,
    list_available: bool = typer.Option(False, "--list", "-l", help="List available pages"),
    preview: Optional[Path] = typer.Option(None, "--preview", help="Save preview PNG instead of pushing"),
):
    """Refresh display page(s)."""
    if list_available:
        typer.echo("Available pages:")
        for name, page_num in list_pages().items():
            typer.echo(f"  {name:12} -> page {page_num}")
        typer.echo("\nAliases:")
        for alias, page_list in ALIASES.items():
            if page_list:
                typer.echo(f"  {alias:12} -> {', '.join(page_list)}")
        return

    # Determine which pages to refresh
    if pages is None:
        pages = "all"

    page_names = []
    for name in pages.split(","):
        name = name.strip().lower()
        if name in ALIASES and ALIASES[name]:
            page_names.extend(ALIASES[name])
        else:
            page_names.append(name)

    try:
        if preview:
            typer.echo(f"Previewing: {', '.join(page_names)} -> {preview}/")
            preview.mkdir(parents=True, exist_ok=True)
        else:
            device = ReTerminalDevice(host)
            caps = device.discover_capabilities(refresh=True)
            unsupported = find_unsupported_legacy_pages(page_names, caps.page_slots)
            if unsupported:
                details = ", ".join(f"{name}->{slot}" for name, slot in unsupported)
                typer.echo(
                    "Error: requested legacy page(s) exceed the live device slot count "
                    f"({caps.page_slots}): {details}"
                )
                typer.echo("Use --preview for those pages or switch to `reterminal publish`.")
                raise typer.Exit(1)

            typer.echo(f"Refreshing: {', '.join(page_names)}")
            typer.echo(f"Device: {caps.host}")
    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Failed to prepare refresh: {e}")
        raise typer.Exit(1)

    success = 0
    for name in page_names:
        entry = get_page(name)
        if entry is None:
            typer.echo(f"Unknown page: {name}")
            continue

        page_class, default_page_num = entry
        typer.echo(f"\n--- {'Previewing' if preview else 'Refreshing'} {name} (page {default_page_num}) ---")

        try:
            page_instance = page_class(host=host)
            data = page_instance.get_data()
            img = page_instance.render(data)

            if preview:
                output_path = preview / f"{name}.png"
                img.save(output_path)
                typer.echo(f"Saved: {output_path}")
            else:
                raw = pil_to_raw(img)
                page_instance.client.push_raw(raw, page=default_page_num)

            success += 1
        except Exception as e:
            logger.error(f"Failed to {'preview' if preview else 'refresh'} {name}: {e}")
            typer.echo(f"Error: {e}")

    typer.echo(f"\n=== Done: {success}/{len(page_names)} pages {'previewed' if preview else 'refreshed'} ===")


@app.command()
def push(
    host: Optional[str] = HostOption,
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Text to display"),
    image: Optional[Path] = typer.Option(None, "--image", "-i", help="Image file to display"),
    qr: Optional[str] = typer.Option(None, "--qr", "-q", help="Generate QR code from text/URL"),
    pattern: Optional[str] = typer.Option(None, "--pattern", "-p", help="Test pattern"),
    page_num: Optional[int] = PageOption,
    font_size: int = typer.Option(48, "--font-size", "-s", help="Font size for text"),
    invert: bool = typer.Option(False, "--invert", help="Invert colors"),
    preview: Optional[Path] = typer.Option(None, "--preview", help="Save preview PNG instead of pushing"),
):
    """Push content to the display."""
    if not any([text, image, pattern, qr]):
        typer.echo("Error: Specify --text, --image, --qr, or --pattern")
        raise typer.Exit(1)

    from PIL import Image, ImageDraw

    img = None
    raw = None

    try:
        if qr:
            try:
                import segno
            except ImportError:
                typer.echo("QR support requires: pip install segno")
                raise typer.Exit(1)

            # Generate QR code
            qr_code = segno.make(qr, error="L")
            # Scale to fit display with padding
            scale = min(WIDTH, HEIGHT) // qr_code.symbol_size()[0] - 2
            scale = max(1, scale)

            # Create white background
            img = Image.new("1", (WIDTH, HEIGHT), color=1)

            # Generate QR as PNG bytes and paste
            import io
            buffer = io.BytesIO()
            qr_code.save(buffer, kind="png", scale=scale, border=2)
            buffer.seek(0)
            qr_img = Image.open(buffer).convert("1")

            # Center QR code
            x = (WIDTH - qr_img.width) // 2
            y = (HEIGHT - qr_img.height) // 2
            img.paste(qr_img, (x, y))

            raw = pil_to_raw(img)

        elif text:
            raw = text_to_raw(text, font_size=font_size)
            # Recreate image for preview
            if preview:
                from reterminal.fonts import load_font
                img = Image.new("1", (WIDTH, HEIGHT), color=1)
                draw = ImageDraw.Draw(img)
                font = load_font(size=font_size)
                lines = text.split("\n")
                line_height = font_size + 10
                y_start = (HEIGHT - len(lines) * line_height) // 2
                for i, line in enumerate(lines):
                    bbox = draw.textbbox((0, 0), line, font=font)
                    x = (WIDTH - (bbox[2] - bbox[0])) // 2
                    draw.text((x, y_start + i * line_height), line, font=font, fill=0)

        elif image:
            if not image.exists():
                typer.echo(f"File not found: {image}")
                raise typer.Exit(1)
            raw = image_to_raw(str(image), invert=invert)
            if preview:
                img = Image.open(image).resize((WIDTH, HEIGHT)).convert("1")

        elif pattern:
            valid_patterns = ["checkerboard", "horizontal", "vertical", "diagonal"]
            if pattern not in valid_patterns:
                typer.echo(f"Invalid pattern. Choose from: {', '.join(valid_patterns)}")
                raise typer.Exit(1)
            raw = create_pattern(pattern)

        # Preview or push
        if preview:
            if img is None:
                typer.echo("Preview not available for this content type")
                raise typer.Exit(1)
            img.save(preview)
            typer.echo(f"Preview saved: {preview}")
        else:
            client = ReTerminal(host)
            result = client.push_raw(raw, page=page_num)
            typer.echo(f"Pushed: {result}")

    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Failed to push: {e}")
        raise typer.Exit(1)


@app.command()
def config():
    """Show current configuration."""
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
    subnet: Optional[str] = typer.Option(None, "--subnet", help="Subnet prefix to scan, e.g. 192.168.7"),
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


@app.command()
def doctor(
    host: Optional[str] = HostOption,
    feed: Optional[Path] = typer.Option(None, "--feed", "-f", help="Optional scene feed JSON to validate"),
    paperclip_url: Optional[str] = typer.Option(None, "--paperclip-url", help="Optional Paperclip-compatible feed URL to validate"),
    include_system: bool = typer.Option(True, "--include-system/--no-include-system", help="Include the built-in system scene in the dry run"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Run operational checks for connectivity, slot truth, and publish-pipeline readiness."""
    try:
        report = run_doctor(
            host,
            feed=feed,
            paperclip_url=paperclip_url,
            include_system=include_system,
        )

        if output == "json":
            payload = {
                "configured_host": report.configured_host,
                "resolved_host": report.resolved_host,
                "reachable": report.reachable,
                "capabilities": report.capabilities.to_dict() if report.capabilities else None,
                "legacy_page_issues": report.legacy_page_issues,
                "scene_count": report.scene_count,
                "assignment_count": report.assignment_count,
                "warnings": report.warnings,
                "errors": report.errors,
            }
            typer.echo(json.dumps(payload, indent=2))
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
            typer.echo(f"  {'Scene Count':20} {report.scene_count}")
            typer.echo(f"  {'Assignments':20} {report.assignment_count}")
        if report.legacy_page_issues:
            typer.echo(
                f"  {'Legacy Mismatch':20} "
                + ", ".join(f"{name}->{slot}" for name, slot in report.legacy_page_issues)
            )
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
        7,
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
):
    """Probe device capabilities before refactoring architecture."""
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


@app.command()
def capabilities(
    host: Optional[str] = HostOption,
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Show the verified host-side device capability contract."""
    try:
        caps = ReTerminalDevice(host).discover_capabilities(refresh=True)
        if output == "json":
            typer.echo(json.dumps(caps.to_dict(), indent=2))
            return

        typer.echo(f"{'─' * 48}")
        typer.echo(f"  reTerminal Capabilities ({caps.host})")
        typer.echo(f"{'─' * 48}")
        typer.echo(f"  {'Resolution':20} {caps.width}x{caps.height}")
        typer.echo(f"  {'Image Bytes':20} {caps.image_bytes}")
        typer.echo(f"  {'Page Slots':20} {caps.page_slots}")
        typer.echo(f"  {'Current Page':20} {caps.current_page}")
        typer.echo(f"  {'Page Name':20} {caps.current_page_name}")
        typer.echo(f"  {'WiFi SSID':20} {caps.ssid}")
        typer.echo(f"  {'RSSI':20} {caps.rssi}")
        typer.echo(f"  {'Uptime':20} {caps.uptime_ms} ms")
        typer.echo(f"{'─' * 48}")
    except Exception as e:
        logger.error(f"Failed to get capabilities: {e}")
        raise typer.Exit(1)


@app.command()
def publish(
    feed: Optional[Path] = typer.Option(None, "--feed", "-f", help="Path to scene feed JSON"),
    paperclip_url: Optional[str] = typer.Option(None, "--paperclip-url", help="Remote Paperclip-compatible scene feed URL"),
    host: Optional[str] = HostOption,
    preview: Optional[Path] = typer.Option(None, "--preview", help="Directory for rendered previews"),
    push: bool = typer.Option(False, "--push", help="Push rendered scenes to the device"),
    include_system: bool = typer.Option(True, "--include-system/--no-include-system", help="Include a built-in ambient system scene"),
    slot_count: Optional[int] = typer.Option(None, "--slots", min=1, help="Override physical slot count"),
    show_slot: Optional[int] = typer.Option(None, "--show-slot", min=0, help="Select which slot is visible after a push"),
    interval: Optional[int] = typer.Option(None, "--interval", min=1, help="Repeat publish every N seconds"),
):
    """Render logical scenes, schedule them into hardware slots, and preview/push them."""
    providers = []
    if feed is not None:
        providers.append(FileSceneProvider(feed))
    if paperclip_url is not None:
        providers.append(PaperclipSceneProvider(paperclip_url))
    if include_system:
        providers.append(SystemSceneProvider())

    if not providers:
        typer.echo("Error: provide --feed, --paperclip-url, or enable --include-system")
        raise typer.Exit(1)
    if show_slot is not None and not push:
        typer.echo("Error: --show-slot requires --push")
        raise typer.Exit(1)

    warn_if_example_feed(feed)

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
            if interval is not None:
                typer.echo(f"\n[{datetime.now().strftime('%H:%M:%S')}] Publish cycle {cycle}")

            result = publisher.publish(
                preview_dir=preview,
                push=push,
                slot_count=slot_count,
                show_slot=current_show_slot,
            )
            target_host = device.discover_capabilities().host if push and device else None
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
def watch(
    page_name: str = typer.Argument("clock", help="Page to watch"),
    host: Optional[str] = HostOption,
    interval: int = typer.Option(60, "--interval", "-i", help="Update interval in seconds"),
    page_num: Optional[int] = PageOption,
):
    """Watch mode - continuously update a legacy page."""
    entry = get_page(page_name)
    if entry is None:
        typer.echo(f"Unknown page: {page_name}")
        raise typer.Exit(1)

    page_class, default_page_num = entry
    target_page = page_num if page_num is not None else default_page_num

    try:
        caps = ReTerminalDevice(host).discover_capabilities(refresh=True)
        unsupported = find_unsupported_legacy_pages([page_name], caps.page_slots)
        if page_num is not None and target_page >= caps.page_slots:
            typer.echo(
                f"Error: slot {target_page} exceeds the live device slot count ({caps.page_slots})."
            )
            raise typer.Exit(1)
        if unsupported and page_num is None:
            typer.echo(
                f"Error: legacy page {page_name} targets slot {default_page_num}, "
                f"but the live device only exposes {caps.page_slots} slot(s)."
            )
            typer.echo("Use --page with a valid slot or switch to `reterminal publish`.")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Failed to prepare watch mode: {e}")
        raise typer.Exit(1)

    typer.echo(f"Watching {page_name} (page {target_page}), interval={interval}s")
    typer.echo("Press Ctrl+C to stop")

    try:
        while True:
            try:
                page_instance = page_class(host=host)
                page_instance.refresh(page=target_page)
                typer.echo(f"[{datetime.now().strftime('%H:%M:%S')}] Updated {page_name}")
            except Exception as e:
                typer.echo(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")

            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("\nStopped watching.")
