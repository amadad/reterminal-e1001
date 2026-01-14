# CLAUDE.md

Project guidance for Claude Code when working with this repository.

## Project Overview

HTTP API firmware and Python client for Seeed reTerminal E1001 - a 7.5" monochrome ePaper display (800x480) powered by ESP32-S3.

**Device IP:** `192.168.7.77`
**Network:** HORUS

## Directory Structure

```
reterminal-e1001/
├── firmware/              # ESP32 PlatformIO project
│   ├── src/main.cpp       # Main firmware (HTTP server, display, buttons)
│   └── platformio.ini     # Build config (USB + OTA environments)
├── python/
│   ├── reterminal.py      # Core client library
│   ├── refresh.py         # Page orchestrator
│   └── pages/             # Page renderers
│       ├── market.py      # VIX, S&P, Dow (from Schwab API)
│       ├── clock.py       # Time and date
│       ├── github.py      # GitHub activity (via gh CLI)
│       └── status.py      # System/clawdbot status
├── refresh.sh             # Shell wrapper for cron
└── .venv/                 # Python virtual environment
```

## Key Commands

```bash
# Refresh pages
./refresh.sh market        # Just market
./refresh.sh all           # All pages

# Build/upload firmware
cd firmware
pio run -e ota -t upload   # OTA (preferred)
pio run -e reterminal -t upload  # USB

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

1. Create `python/pages/mypage.py`:
```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from reterminal import ReTerminal, WIDTH, HEIGHT, IMAGE_BYTES
from PIL import Image, ImageDraw, ImageFont

def get_data():
    # Fetch your data
    return {"value": 42}

def render(data: dict) -> bytes:
    img = Image.new("1", (WIDTH, HEIGHT), color=1)  # White background
    draw = ImageDraw.Draw(img)
    # Draw your content...
    # Convert to raw bytes (1 = black)
    raw = bytearray(IMAGE_BYTES)
    pixels = img.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_idx = (y * WIDTH + x) // 8
            bit_idx = 7 - (x % 8)
            if not pixels[x, y]:  # Black pixel
                raw[byte_idx] |= (1 << bit_idx)
    return bytes(raw)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--page", type=int)
    args = parser.parse_args()

    data = get_data()
    rt = ReTerminal(args.host)
    rt.push_raw(render(data), page=args.page)

if __name__ == "__main__":
    main()
```

2. Register in `python/refresh.py`:
```python
PAGES = {
    # ...existing pages...
    "mypage": ("pages/mypage.py", 3),  # Assign page number
}
```

## Data Sources

| Source | Location | Used By |
|--------|----------|---------|
| Schwab Market API | `~/Desktop/base/agent-alpha` | market.py |
| GitHub CLI | `gh` command | github.py |
| Clawdbot | `clawdbot health` | status.py |

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
| Black background | Bitmap encoding inverted; check `not pixels[x, y]` |
| Buttons not working | Ensure INPUT_PULLUP; buttons are active LOW |

## Related

- **Clawdbot skill:** `~/Desktop/base/clawdbot/skills/reterminal/`
- **Agent-alpha (market data):** `~/Desktop/base/agent-alpha/`
