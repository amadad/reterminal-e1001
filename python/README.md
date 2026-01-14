# Python Client

Python library and page renderers for reTerminal E1001.

## Install

```bash
pip install -r requirements.txt
```

## Structure

```
python/
├── reterminal.py      # Core client library
├── refresh.py         # Page orchestrator
├── requirements.txt
└── pages/             # Page renderers
    ├── market.py      # VIX, S&P, Dow
    ├── clock.py       # Time and date
    ├── github.py      # GitHub activity
    └── status.py      # System status
```

## Usage

### Client Library

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

# Status
print(rt.status())
rt.beep()
```

### CLI

```bash
python reterminal.py --host 192.168.7.77 --text "Hello" --page 0
python reterminal.py --host 192.168.7.77 --image photo.png --page 1
python reterminal.py --host 192.168.7.77 --status
python reterminal.py --host 192.168.7.77 --beep
```

### Page Orchestrator

```bash
# Refresh specific page
python refresh.py --page market
python refresh.py --page clock

# Refresh multiple
python refresh.py --page market,clock

# Refresh all
python refresh.py --page all

# List available pages
python refresh.py --list
```

## Pages

| Name | Page # | Description |
|------|--------|-------------|
| market | 0 | VIX, S&P 500, Dow (from Schwab) |
| clock | 1 | Time and date |
| github | 2 | GitHub activity (via gh CLI) |
| status | 3 | System/Clawdbot status |

## Adding a Page

1. Create `pages/mypage.py`:

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from reterminal import ReTerminal, WIDTH, HEIGHT, IMAGE_BYTES
from PIL import Image, ImageDraw, ImageFont

def get_data():
    return {"value": 42}

def render(data: dict) -> bytes:
    img = Image.new("1", (WIDTH, HEIGHT), color=1)
    draw = ImageDraw.Draw(img)
    draw.text((50, 100), f"Value: {data['value']}", fill=0)

    # Convert to raw bytes
    raw = bytearray(IMAGE_BYTES)
    pixels = img.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            byte_idx = (y * WIDTH + x) // 8
            bit_idx = 7 - (x % 8)
            if not pixels[x, y]:  # Black = set bit
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

2. Register in `refresh.py`:

```python
PAGES = {
    ...
    "mypage": ("pages/mypage.py", 3),
}
```

3. Test:

```bash
python refresh.py --page mypage
```
