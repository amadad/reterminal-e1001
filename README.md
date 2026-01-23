# reTerminal E1001

HTTP API firmware and Python CLI for Seeed reTerminal E1001 ePaper display.

![reTerminal E1001](https://files.seeedstudio.com/wiki/reterminal_e10xx/img/132.jpg)

## Features

- **7-Page Carousel** - Market, clock, GitHub, status, portfolio, dashboard, weather
- **Modern CLI** - Typer-based with rich output, retry logic, preview mode
- **Physical Buttons** - Navigate pages without network
- **HTTP API** - Push images, control pages, trigger buzzer
- **OTA Updates** - Flash firmware over WiFi
- **QR Code Support** - Generate QR codes for WiFi, URLs, etc.
- **Watch Mode** - Continuous page updates

## Hardware

- **Display:** 7.5" monochrome ePaper (800x480)
- **MCU:** ESP32-S3 with PSRAM
- **Buttons:** 3 tactile (prev/next/refresh)
- **Buzzer:** Piezo feedback

## Quick Start

### 1. Flash Firmware

```bash
cd firmware
pio run -e reterminal -t upload  # USB first time
pio run -e ota -t upload         # WiFi after
```

### 2. Install Python Package

```bash
cd python
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Optional: QR code support
pip install segno
```

### 3. Configure

```bash
# Copy and edit environment
cp .env.example .env

# Or use environment variables
export RETERMINAL_HOST=192.168.7.77
```

### 4. Use CLI

```bash
# Check device
python -m reterminal status
python -m reterminal config

# Refresh pages
python -m reterminal refresh market
python -m reterminal refresh all

# Push content
python -m reterminal push --text "Hello World"
python -m reterminal push --qr "https://example.com"

# Preview without pushing (renders to PNG)
python -m reterminal refresh market --preview ./previews/
```

## CLI Commands

```
reterminal status      Get device status
reterminal beep        Trigger buzzer (supports -n count)
reterminal buttons     Get button states (supports --watch)
reterminal page        Get/set current page (next, prev, 0-6)
reterminal refresh     Refresh display pages
reterminal push        Push text, image, QR code, or pattern
reterminal watch       Continuous page updates
reterminal config      Show current configuration
```

## Pages

| Page | Name | Content | Data Source |
|------|------|---------|-------------|
| 0 | market | VIX, S&P 500, Dow | Schwab API |
| 1 | clock | Time and date | Local |
| 2 | github | Activity and stats | gh CLI |
| 3 | status | System/Clawdbot | Local |
| 4 | portfolio | Account summary | Schwab snapshots |
| 5 | dashboard | System info | Local |
| 6 | weather | Current conditions | Open-Meteo API |

## Project Structure

```
reterminal-e1001/
├── firmware/                  # ESP32 PlatformIO project
│   ├── src/main.cpp
│   └── platformio.ini
├── python/
│   ├── pyproject.toml         # Package config
│   ├── .env.example           # Environment template
│   └── reterminal/            # Python package
│       ├── __init__.py
│       ├── __main__.py        # CLI entry point
│       ├── client.py          # HTTP client + retry
│       ├── config.py          # Settings from env
│       ├── encoding.py        # Pixel encoding
│       ├── fonts.py           # Platform font detection
│       ├── cli/               # Typer CLI
│       │   ├── app.py
│       │   └── commands.py
│       └── pages/             # Display pages
│           ├── base.py        # BasePage class
│           ├── market.py
│           ├── clock.py
│           ├── github.py
│           ├── status.py
│           ├── portfolio.py
│           ├── dashboard.py
│           └── weather.py
├── refresh.sh                 # Shell wrapper for cron
├── CLAUDE.md                  # AI agent guidance
└── AGENTS.md                  # Agent instructions
```

## API Reference

### HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Device status (IP, RSSI, uptime) |
| `/buttons` | GET | Button states |
| `/beep` | GET | Trigger buzzer |
| `/page` | GET | Current page info |
| `/page` | POST | Set page: `{"page": 0}` or `{"action": "next"}` |
| `/imageraw` | POST | Upload image (multipart form) |

### Python Client

```python
from reterminal import ReTerminal

# Uses RETERMINAL_HOST env var or default
rt = ReTerminal()

# Or specify host
rt = ReTerminal("192.168.7.77")

# Push content
rt.push_text("Hello World", page=0, font_size=48)
rt.push_image("photo.png", page=1)

# Navigation
rt.next_page()
rt.prev_page()
rt.set_page(2)

# Device
rt.status()
rt.beep()
```

## Configuration

Environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `RETERMINAL_HOST` | 192.168.7.77 | Device IP |
| `RETERMINAL_TIMEOUT` | 30 | Request timeout (seconds) |
| `RETERMINAL_LOG_LEVEL` | INFO | Logging level |
| `RETERMINAL_RETRY_ATTEMPTS` | 3 | Retry count |
| `RETERMINAL_RETRY_MIN_WAIT` | 1 | Min retry wait (seconds) |
| `RETERMINAL_RETRY_MAX_WAIT` | 10 | Max retry wait (seconds) |

## Adding Pages

Create a new page by subclassing `BasePage`:

```python
# python/reterminal/pages/mypage.py
from reterminal.pages.base import BasePage
from reterminal.pages import register

@register("mypage", page_number=7)
class MyPage(BasePage):
    name = "mypage"
    description = "My custom page"

    def get_data(self):
        return {"value": 42}

    def render(self, data):
        img, draw = self.create_canvas()
        fonts = self.load_fonts()
        draw.text((50, 50), f"Value: {data['value']}", font=fonts["large"], fill=0)
        return img
```

Then import in `pages/__init__.py`:

```python
from reterminal.pages import mypage
```

## Image Format

- **Resolution:** 800x480 pixels
- **Format:** 1-bit monochrome
- **Size:** 48,000 bytes
- **Encoding:** 1 = black, 0 = white (GxEPD2)

## Cron Schedule

Market data auto-refreshes at:
- 6:30 AM PT (market open)
- 1:00 PM PT (market close)

```bash
# Edit crontab
crontab -e

# Example entries
30 6 * * 1-5 cd ~/base/projects/reterminal-e1001 && ./refresh.sh market
0 13 * * 1-5 cd ~/base/projects/reterminal-e1001 && ./refresh.sh market
```

## Credits

Hardware reference from [Handy4ndy/Handy-reTerminal-E1001](https://github.com/Handy4ndy/Handy-reTerminal-E1001)

## License

MIT
