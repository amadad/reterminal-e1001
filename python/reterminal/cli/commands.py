"""CLI commands for reterminal."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from reterminal.cli.app import app
from reterminal.client import ReTerminal
from reterminal.config import settings, get_host, WIDTH, HEIGHT
from reterminal.encoding import text_to_raw, image_to_raw, create_pattern, pil_to_raw
from reterminal.pages import get_page, list_pages, ALIASES


# Common options
HostOption = typer.Option(None, "--host", "-h", help="Device IP address")
PageOption = typer.Option(None, "--page", help="Page to store (0-3)")


@app.command()
def status(
    host: Optional[str] = HostOption,
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json"),
):
    """Get device status."""
    client = ReTerminal(host)
    try:
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
    client = ReTerminal(host)
    try:
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
    client = ReTerminal(host)
    try:
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
    client = ReTerminal(host)
    try:
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

    if preview:
        typer.echo(f"Previewing: {', '.join(page_names)} -> {preview}/")
        preview.mkdir(parents=True, exist_ok=True)
    else:
        typer.echo(f"Refreshing: {', '.join(page_names)}")
        typer.echo(f"Device: {get_host(host)}")

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

    except Exception as e:
        logger.error(f"Failed to push: {e}")
        raise typer.Exit(1)


@app.command()
def config():
    """Show current configuration."""
    typer.echo(f"{'─' * 40}")
    typer.echo("  reTerminal Configuration")
    typer.echo(f"{'─' * 40}")
    typer.echo(f"  {'Host':20} {settings.host}")
    typer.echo(f"  {'Timeout':20} {settings.timeout}s")
    typer.echo(f"  {'Log Level':20} {settings.log_level}")
    typer.echo(f"  {'Retry Attempts':20} {settings.retry_attempts}")
    typer.echo(f"  {'Retry Wait':20} {settings.retry_min_wait}-{settings.retry_max_wait}s")
    typer.echo(f"{'─' * 40}")
    typer.echo("\nSet via environment variables (RETERMINAL_*) or .env file")


@app.command()
def watch(
    page_name: str = typer.Argument("clock", help="Page to watch"),
    host: Optional[str] = HostOption,
    interval: int = typer.Option(60, "--interval", "-i", help="Update interval in seconds"),
    page_num: Optional[int] = PageOption,
):
    """Watch mode - continuously update a page."""
    entry = get_page(page_name)
    if entry is None:
        typer.echo(f"Unknown page: {page_name}")
        raise typer.Exit(1)

    page_class, default_page_num = entry
    target_page = page_num if page_num is not None else default_page_num

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
