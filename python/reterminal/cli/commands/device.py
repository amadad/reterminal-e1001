"""Direct device operations: status, beep, buttons, page, clear, push, snapshot, capabilities."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from reterminal.cli._typer_app import app
from reterminal.cli.commands._shared import (
    HostOption,
    PageOption,
    emit_output,
    require_live_action,
)
from reterminal.client import ReTerminal
from reterminal.config import WIDTH, HEIGHT
from reterminal.device import ReTerminalDevice
from reterminal.encoding import text_to_raw, image_to_raw, create_pattern, pil_to_raw, raw_to_pil


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
    live: bool = typer.Option(False, "--live", help="Confirm a live device mutation"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Fail instead of mutating the live device"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Trigger the buzzer."""
    require_live_action("beep", live=live, non_interactive=non_interactive)
    try:
        client = ReTerminal(host)
        for i in range(count):
            client.beep()
            if i < count - 1:
                time.sleep(delay)
        payload = {"host": client.host, "count": count, "delay": delay, "status": "ok"}
        if not emit_output(payload, output):
            typer.echo(f"Beeped {count}x!")
    except Exception as e:
        logger.error(f"Failed to beep: {e}")
        raise typer.Exit(1)


@app.command()
def buttons(
    host: Optional[str] = HostOption,
    watch: bool = typer.Option(False, "--watch", "-w", help="Watch button states continuously"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Get button states."""
    try:
        client = ReTerminal(host)
        if watch:
            if output == "json":
                typer.echo("Error: --watch does not support JSON output.")
                raise typer.Exit(1)
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
            if not emit_output({"host": client.host, "buttons": result}, output):
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
    live: bool = typer.Option(False, "--live", help="Confirm a live device mutation"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Fail instead of mutating the live device"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Get or set current page. Use 'next', 'prev', or a page number."""
    try:
        if action is None:
            client = ReTerminal(host)
            result = client.get_page()
        elif action == "next":
            require_live_action("page next", live=live, non_interactive=non_interactive)
            client = ReTerminal(host)
            result = client.next_page()
        elif action == "prev":
            require_live_action("page prev", live=live, non_interactive=non_interactive)
            client = ReTerminal(host)
            result = client.prev_page()
        else:
            try:
                page_num = int(action)
            except ValueError:
                typer.echo(f"Invalid action: {action}. Use 'next', 'prev', or a number.")
                raise typer.Exit(1)
            require_live_action("page set", live=live, non_interactive=non_interactive)
            client = ReTerminal(host)
            result = client.set_page(page_num)

        if not emit_output({"host": client.host, "page": result}, output):
            typer.echo(f"Page: {result.get('page', '?')} ({result.get('name', 'unknown')})")
    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Failed to manage page: {e}")
        raise typer.Exit(1)


@app.command()
def clear(
    host: Optional[str] = HostOption,
    page_num: Optional[int] = PageOption,
    clear_all: bool = typer.Option(False, "--all", help="Clear all cached slots and blank the display"),
    live: bool = typer.Option(False, "--live", help="Confirm a live device mutation"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Fail instead of mutating the live device"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Clear one cached slot or the full volatile device cache."""
    if clear_all and page_num is not None:
        typer.echo("Error: --all cannot be combined with --page")
        raise typer.Exit(1)

    require_live_action("clear", live=live, non_interactive=non_interactive)

    try:
        device = ReTerminalDevice(host)
        result = device.clear(page_num, all=clear_all)
        payload = {"host": device.client.host, "result": result}
        if not emit_output(payload, output):
            typer.echo(json.dumps(result, indent=2))
    except Exception as e:
        logger.error(f"Failed to clear device cache: {e}")
        raise typer.Exit(1)


@app.command()
def push(
    host: Optional[str] = HostOption,
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Text to display"),
    image: Optional[Path] = typer.Option(None, "--image", "-i", help="Image file to display"),
    qr: Optional[str] = typer.Option(None, "--qr", "-q", help="Generate QR code from text/URL"),
    pattern: Optional[str] = typer.Option(None, "--pattern", "-p", help="Test pattern"),
    page_num: Optional[int] = PageOption,
    transient: bool = typer.Option(False, "--transient", help="Display directly without storing in a slot"),
    font_size: int = typer.Option(48, "--font-size", "-s", help="Font size for text"),
    invert: bool = typer.Option(False, "--invert", help="Invert colors"),
    preview: Optional[Path] = typer.Option(None, "--preview", help="Save preview PNG instead of pushing"),
    live: bool = typer.Option(False, "--live", help="Confirm a live device mutation"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Fail instead of mutating the live device"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Push content to the display."""
    if not any([text, image, pattern, qr]):
        typer.echo("Error: Specify --text, --image, --qr, or --pattern")
        raise typer.Exit(1)

    if transient and page_num is not None:
        typer.echo("Error: --transient cannot be combined with --page")
        raise typer.Exit(1)
    if preview is None:
        require_live_action("push", live=live, non_interactive=non_interactive)
        if page_num is None and not transient:
            typer.echo("Error: live push requires --page. Use --transient for direct display-only pushes.")
            raise typer.Exit(1)

    from PIL import Image, ImageDraw

    img = None
    raw = None
    content_type = "text" if text else "image" if image else "qr" if qr else "pattern"

    try:
        if qr:
            try:
                import segno
            except ImportError:
                typer.echo("QR support requires: pip install segno")
                raise typer.Exit(1)

            qr_code = segno.make(qr, error="L")
            scale = min(WIDTH, HEIGHT) // qr_code.symbol_size()[0] - 2
            scale = max(1, scale)

            img = Image.new("1", (WIDTH, HEIGHT), color=1)

            import io
            buffer = io.BytesIO()
            qr_code.save(buffer, kind="png", scale=scale, border=2)
            buffer.seek(0)
            qr_img = Image.open(buffer).convert("1")

            x = (WIDTH - qr_img.width) // 2
            y = (HEIGHT - qr_img.height) // 2
            img.paste(qr_img, (x, y))

            raw = pil_to_raw(img)

        elif text:
            raw = text_to_raw(text, font_size=font_size)
            if preview:
                from reterminal.fonts import load_font
                img = Image.new("1", (WIDTH, HEIGHT), color=1)
                draw = ImageDraw.Draw(img)
                draw.fontmode = "1"
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

        if preview:
            if img is None:
                typer.echo("Preview not available for this content type")
                raise typer.Exit(1)
            preview.parent.mkdir(parents=True, exist_ok=True)
            img.save(preview)
            payload = {
                "mode": "preview",
                "content_type": content_type,
                "page": page_num,
                "transient": transient,
                "preview_path": str(preview),
            }
            if not emit_output(payload, output):
                typer.echo(f"Preview saved: {preview}")
        else:
            client = ReTerminal(host)
            result = client.push_raw(raw, page=page_num)
            payload = {
                "mode": "live",
                "content_type": content_type,
                "host": client.host,
                "page": page_num,
                "transient": transient,
                "result": result,
            }
            if not emit_output(payload, output):
                typer.echo(f"Pushed: {result}")

    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Failed to push: {e}")
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
        if caps.hostname is not None:
            typer.echo(f"  {'Hostname':20} {caps.hostname}")
        if caps.firmware_version is not None:
            typer.echo(f"  {'Firmware':20} {caps.firmware_version}")
        if caps.build_sha is not None:
            typer.echo(f"  {'Build SHA':20} {caps.build_sha}")
        if caps.build_time is not None:
            typer.echo(f"  {'Build Time':20} {caps.build_time}")
        if caps.snapshot_readback is not None:
            typer.echo(f"  {'Snapshot Readback':20} {'yes' if caps.snapshot_readback else 'no'}")
        if caps.loaded_pages:
            loaded = ", ".join(str(index) for index, value in enumerate(caps.loaded_pages) if value) or "none"
            typer.echo(f"  {'Loaded Slots':20} {loaded}")
        typer.echo(f"  {'WiFi SSID':20} {caps.ssid}")
        typer.echo(f"  {'RSSI':20} {caps.rssi}")
        if caps.reset_reason is not None:
            typer.echo(f"  {'Reset Reason':20} {caps.reset_reason}")
        if caps.wifi_reconnect_attempts is not None:
            typer.echo(f"  {'WiFi Reconnects':20} {caps.wifi_reconnect_attempts}")
        if caps.wifi_down_ms is not None:
            typer.echo(f"  {'WiFi Down':20} {caps.wifi_down_ms} ms")
        if caps.self_restart_count is not None:
            typer.echo(f"  {'Self Restarts':20} {caps.self_restart_count}")
        if caps.last_self_restart_reason is not None:
            typer.echo(f"  {'Last Self Restart':20} {caps.last_self_restart_reason}")
        if caps.loop_watchdog_armed is not None:
            typer.echo(f"  {'Loop Watchdog':20} {'armed' if caps.loop_watchdog_armed else 'not armed'}")
        typer.echo(f"  {'Uptime':20} {caps.uptime_ms} ms")
        typer.echo(f"{'─' * 48}")
    except Exception as e:
        logger.error(f"Failed to get capabilities: {e}")
        raise typer.Exit(1)


@app.command()
def snapshot(
    host: Optional[str] = HostOption,
    page_num: Optional[int] = PageOption,
    raw_path: Optional[Path] = typer.Option(None, "--raw", help="Write raw 1-bit bitmap bytes to a file"),
    png_path: Optional[Path] = typer.Option(None, "--png", help="Write a decoded PNG preview to a file"),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Fetch a stored slot bitmap back from the device."""
    try:
        device = ReTerminalDevice(host)
        result = device.snapshot(page_num)
        payload = result.to_dict()

        if raw_path is not None:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(result.raw)
            payload["raw_path"] = str(raw_path)

        if png_path is not None:
            png_path.parent.mkdir(parents=True, exist_ok=True)
            raw_to_pil(result.raw).save(png_path)
            payload["png_path"] = str(png_path)

        if emit_output(payload, output):
            return

        typer.echo(f"Snapshot host: {result.host}")
        typer.echo(f"Slot: {result.page}")
        typer.echo(f"Name: {result.page_name or 'unknown'}")
        typer.echo(f"Dimensions: {result.width}x{result.height}")
        typer.echo(f"Image bytes: {result.image_bytes}")
        typer.echo(f"SHA256: {result.sha256}")
        if raw_path is not None:
            typer.echo(f"Raw saved: {raw_path}")
        if png_path is not None:
            typer.echo(f"PNG saved: {png_path}")
    except Exception as e:
        logger.error(f"Failed to fetch snapshot: {e}")
        raise typer.Exit(1)
