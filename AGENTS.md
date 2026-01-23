# AGENTS.md

Instructions for AI agents working with this repository.

## What This Is

reTerminal E1001 is a 7.5" ePaper display connected to the local network. It shows a 7-page carousel of information that can be navigated with physical buttons or controlled via HTTP API and CLI.

## Device Details

- **IP:** 192.168.7.77
- **Display:** 800x480 monochrome ePaper
- **Refresh:** ~3 seconds (slow - minimize updates)

## CLI Reference

The CLI is invoked via `python -m reterminal` from the `python/` directory:

```bash
cd ~/base/projects/reterminal-e1001/python
source ../.venv/bin/activate

# Or with environment
export RETERMINAL_HOST=192.168.7.77
```

### Commands

| Command | Description | Example |
|---------|-------------|---------|
| `status` | Device status | `python -m reterminal status` |
| `config` | Show settings | `python -m reterminal config` |
| `beep` | Trigger buzzer | `python -m reterminal beep -n 3` |
| `buttons` | Button states | `python -m reterminal buttons --watch` |
| `page` | Page control | `python -m reterminal page next` |
| `refresh` | Update pages | `python -m reterminal refresh market` |
| `push` | Push content | `python -m reterminal push --text "Hi"` |
| `watch` | Continuous updates | `python -m reterminal watch clock -i 60` |

### Common Operations

```bash
# Check device is reachable
python -m reterminal status

# Refresh specific page
python -m reterminal refresh market

# Refresh all pages
python -m reterminal refresh all

# Push custom text
python -m reterminal push --text "Hello World" --page 0

# Push QR code
python -m reterminal push --qr "https://example.com"

# Preview without pushing (renders to PNG)
python -m reterminal refresh market --preview ./output/

# Navigate pages
python -m reterminal page next
python -m reterminal page 0

# Watch mode (continuous updates)
python -m reterminal watch clock -i 30
```

### Shell Wrapper (for cron)

```bash
./refresh.sh market   # Single page
./refresh.sh all      # All pages
```

## Page Assignments

| Page | Name | Content |
|------|------|---------|
| 0 | market | VIX, S&P 500, Dow Jones |
| 1 | clock | Time and date |
| 2 | github | GitHub activity |
| 3 | status | System status |
| 4 | portfolio | Account summary |
| 5 | dashboard | System info |
| 6 | weather | Current conditions |

List pages: `python -m reterminal refresh --list`

## Adding Content

To add a new page:

1. Create `python/reterminal/pages/newpage.py`:

```python
from reterminal.pages.base import BasePage
from reterminal.pages import register

@register("newpage", page_number=7)
class NewPage(BasePage):
    name = "newpage"

    def get_data(self):
        return {"message": "Hello"}

    def render(self, data):
        img, draw = self.create_canvas()
        fonts = self.load_fonts()
        draw.text((50, 50), data["message"], font=fonts["large"], fill=0)
        return img
```

2. Import in `python/reterminal/pages/__init__.py`:

```python
from reterminal.pages import newpage
```

3. Test: `python -m reterminal refresh newpage`

## Important Notes

- **Minimize refreshes** - ePaper flickers on update; don't refresh frequently
- **Preview mode** - Use `--preview DIR` to test rendering without pushing
- **White background** - Use `self.create_canvas()` for correct encoding
- **Market data** - Requires Schwab auth in schwab-cli-tools project
- **Weather** - Uses Open-Meteo API (free, no key required)
- **Retry logic** - Client retries 3x with exponential backoff on failures

## Configuration

Set via environment or `.env` file in `python/`:

```bash
RETERMINAL_HOST=192.168.7.77
RETERMINAL_TIMEOUT=30
RETERMINAL_LOG_LEVEL=INFO
RETERMINAL_RETRY_ATTEMPTS=3
```

View current config: `python -m reterminal config`

## Firmware Updates

```bash
cd ~/base/projects/reterminal-e1001/firmware
pio run -e ota -t upload  # OTA over WiFi (preferred)
```

Only update firmware if display behavior needs changing. Page content changes are Python-only.

## When to Update Display

Good reasons:
- User explicitly requests it
- Scheduled cron (market open/close)
- Significant event (alert, notification)

Bad reasons:
- Every few seconds/minutes
- Testing (use `--preview` or `/status` instead)
- Multiple rapid updates

## Integration Points

- **Clawdbot:** Skill at `~/base/clawdbot/skills/reterminal/`
- **Telegram:** Can trigger via clawdbot min bot
- **Cron:** Auto-refresh at 6:30 AM and 1:00 PM PT (Mon-Fri)

## Debugging

```bash
# Verbose output
python -m reterminal -v refresh market

# Check configuration
python -m reterminal config

# Preview rendering
python -m reterminal refresh all --preview /tmp/previews/

# Test connection with short timeout
RETERMINAL_TIMEOUT=5 python -m reterminal status
```
