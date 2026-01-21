# reTerminal E1001

HTTP API firmware and Python client for [Seeed reTerminal E1001 ePaper display](https://wiki.seeedstudio.com/getting_started_with_reterminal_e1001/).

![reTerminal E1001](https://files.seeedstudio.com/wiki/reterminal_e10xx/img/132.jpg)

## Features

- **4-Page Carousel** - Market data, clock, GitHub activity, system status
- **Physical Buttons** - Navigate pages without network
- **HTTP API** - Push images, control pages, trigger buzzer
- **OTA Updates** - Flash firmware over WiFi
- **Python Client** - Simple library for rendering and pushing content

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

### 2. Install Python Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r python/requirements.txt
```

### 3. Push Content

```bash
# Refresh all pages
./refresh.sh all

# Refresh specific page
./refresh.sh market
./refresh.sh clock
```

## Pages

| Page | Content | Data Source |
|------|---------|-------------|
| 0 | Market Pulse | VIX, S&P 500, Dow (Schwab API) |
| 1 | Clock | Local time and date |
| 2 | GitHub | Activity and stats (gh CLI) |
| 3 | Status | System and Clawdbot status |

## Project Structure

```
reterminal-e1001/
├── firmware/              # ESP32 PlatformIO project
│   ├── src/main.cpp
│   └── platformio.ini
├── python/
│   ├── reterminal.py      # Client library
│   ├── refresh.py         # Page orchestrator
│   └── pages/             # Page renderers
│       ├── market.py
│       ├── clock.py
│       ├── github.py
│       └── status.py
├── refresh.sh             # Shell wrapper
├── CLAUDE.md              # AI agent guidance
├── AGENTS.md              # Agent instructions
└── README.md
```

## API Reference

### Endpoints

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

rt = ReTerminal("192.168.7.77")

# Push text
rt.push_text("Hello World", page=0, font_size=48)

# Push image
rt.push_image("photo.png", page=1)

# Navigation
rt.next_page()
rt.prev_page()
rt.set_page(2)

# Device
rt.status()
rt.beep()
```

### CLI

```bash
# Push text
python python/reterminal.py --host 192.168.7.77 --text "Hello" --page 0

# Push image
python python/reterminal.py --host 192.168.7.77 --image photo.png --page 1

# Check status
python python/reterminal.py --host 192.168.7.77 --status
```

## Adding Pages

1. Create `python/pages/mypage.py`:

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from reterminal import ReTerminal, WIDTH, HEIGHT, IMAGE_BYTES
from PIL import Image, ImageDraw, ImageFont

def render() -> bytes:
    img = Image.new("1", (WIDTH, HEIGHT), color=1)
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "My Page", fill=0)
    # Convert to raw (see CLAUDE.md for full template)
    ...

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--page", type=int)
    args = parser.parse_args()

    rt = ReTerminal(args.host)
    rt.push_raw(render(), page=args.page)

if __name__ == "__main__":
    main()
```

2. Register in `python/refresh.py`:

```python
PAGES = {
    ...
    "mypage": ("pages/mypage.py", 3),
}
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

Minimal refreshes to reduce ePaper flicker.

## Credits

Hardware reference from [Handy4ndy/Handy-reTerminal-E1001](https://github.com/Handy4ndy/Handy-reTerminal-E1001)

## License

MIT
