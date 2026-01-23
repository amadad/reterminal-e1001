# CLAUDE.md

Project guidance for Claude Code when working with this repository.

## Project Overview

HTTP API firmware and Python CLI for Seeed reTerminal E1001 - a 7.5" monochrome ePaper display (800x480) powered by ESP32-S3.

**Device IP:** `192.168.7.77`
**Network:** HORUS

## Directory Structure

```
reterminal-e1001/
├── firmware/                  # ESP32 PlatformIO project
│   ├── src/main.cpp           # HTTP server, display, buttons
│   └── platformio.ini         # USB + OTA environments
├── python/
│   ├── pyproject.toml         # Package dependencies
│   ├── .env.example           # Environment template
│   └── reterminal/            # Main package
│       ├── __init__.py        # Public exports
│       ├── __main__.py        # python -m reterminal
│       ├── client.py          # HTTP client + tenacity retry
│       ├── config.py          # Settings from env vars
│       ├── encoding.py        # Pixel encoding (single source)
│       ├── exceptions.py      # Custom exceptions
│       ├── fonts.py           # Platform-aware font loading
│       ├── cli/
│       │   ├── app.py         # Typer app + loguru
│       │   └── commands.py    # CLI commands
│       └── pages/
│           ├── base.py        # BasePage abstract class
│           ├── market.py      # VIX, S&P, Dow (Schwab)
│           ├── clock.py       # Time and date
│           ├── github.py      # GitHub activity (gh CLI)
│           ├── status.py      # System/clawdbot status
│           ├── portfolio.py   # Account summary (Schwab)
│           ├── dashboard.py   # System info
│           └── weather.py     # Open-Meteo API
├── refresh.sh                 # Shell wrapper for cron
└── .venv/                     # Virtual environment
```

## Key Commands

```bash
# CLI usage
python -m reterminal status              # Device status
python -m reterminal config              # Show configuration
python -m reterminal refresh market      # Refresh single page
python -m reterminal refresh all         # Refresh all pages
python -m reterminal push --text "Hi"    # Push text
python -m reterminal push --qr "URL"     # Push QR code
python -m reterminal watch clock -i 60   # Watch mode

# Preview without pushing (useful for testing)
python -m reterminal refresh market --preview ./previews/

# Shell wrapper (for cron)
./refresh.sh market
./refresh.sh all

# Firmware
cd firmware
pio run -e ota -t upload                 # OTA (preferred)
pio run -e reterminal -t upload          # USB

# Test device
curl http://192.168.7.77/status
curl http://192.168.7.77/beep
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Device status |
| `/buttons` | GET | Button states |
| `/beep` | GET | Trigger buzzer |
| `/page` | GET/POST | Get/set current page |
| `/imageraw` | POST | Upload image (multipart, 48000 bytes) |

## Image Format

- **Resolution:** 800x480 pixels
- **Format:** 1-bit monochrome, MSB first
- **Size:** 48000 bytes (800 * 480 / 8)
- **Encoding:** 1 = black pixel, 0 = white pixel (GxEPD2 convention)

## Adding a New Page

1. Create `python/reterminal/pages/mypage.py`:

```python
from typing import Any, Dict
from PIL import Image
from reterminal.pages.base import BasePage
from reterminal.pages import register

@register("mypage", page_number=7)
class MyPage(BasePage):
    """My custom page."""

    name = "mypage"
    description = "Description here"

    def get_data(self) -> Dict[str, Any]:
        """Fetch data for the page."""
        return {"value": 42}

    def render(self, data: Dict[str, Any]) -> Image.Image:
        """Render data to PIL Image."""
        img, draw = self.create_canvas()
        fonts = self.load_fonts()

        draw.text((50, 30), "MY PAGE", font=fonts["title"], fill=0)
        draw.text((50, 100), f"Value: {data['value']}", font=fonts["large"], fill=0)

        self.draw_divider(draw, 180)
        self.add_timestamp(draw, fonts["small"])

        return img
```

2. Import in `python/reterminal/pages/__init__.py`:

```python
from reterminal.pages import mypage
```

## Configuration

Environment variables (RETERMINAL_* prefix):

| Variable | Default | Description |
|----------|---------|-------------|
| `RETERMINAL_HOST` | 192.168.7.77 | Device IP |
| `RETERMINAL_TIMEOUT` | 30 | Request timeout |
| `RETERMINAL_LOG_LEVEL` | INFO | Log level |
| `RETERMINAL_RETRY_ATTEMPTS` | 3 | Retry count |

## Data Sources

| Source | Location | Used By |
|--------|----------|---------|
| Schwab API | `~/base/projects/schwab-cli-tools` | market.py, portfolio.py |
| GitHub CLI | `gh` command | github.py |
| Clawdbot | `clawdbot health` | status.py |
| Open-Meteo | Free API (no key) | weather.py |

## Cron Schedule

Market page refreshes at:
- 6:30 AM PT (market open)
- 1:00 PM PT (market close)

Edit with `crontab -e`. Kept minimal to reduce ePaper flicker.

## Hardware Notes

- **MCU:** ESP32-S3 with PSRAM
- **Display:** GxEPD2_750_GDEY075T7 (7.5" Goodisplay)
- **Buttons:** GPIO 3 (right), 4 (middle), 5 (left)
- **Buzzer:** GPIO 45
- **USB Serial:** GPIO 44/43 (Serial1)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Device unreachable | Check WiFi; device may have new IP |
| OTA fails | Verify IP in platformio.ini matches device |
| Black background | Use `self.create_canvas()` - handles encoding |
| Buttons not working | Ensure INPUT_PULLUP; buttons are active LOW |
| Import errors | Run from `python/` dir or install package |

## Code Patterns

### Using the client directly

```python
from reterminal import ReTerminal, settings

rt = ReTerminal()  # Uses RETERMINAL_HOST
rt.status()
rt.push_text("Hello", page=0)
```

### Using encoding utilities

```python
from reterminal.encoding import pil_to_raw, text_to_raw
from PIL import Image

# From PIL Image
img = Image.new("1", (800, 480), color=1)
raw = pil_to_raw(img)

# From text
raw = text_to_raw("Hello World", font_size=72)
```

### Retry behavior

The client uses tenacity for automatic retries:
- 3 attempts by default
- Exponential backoff (1-10 seconds)
- Retries on connection errors and timeouts

## Related

- **Clawdbot skill:** `~/Desktop/base/clawdbot/skills/reterminal/`
- **Schwab tools:** `~/base/projects/schwab-cli-tools/`
