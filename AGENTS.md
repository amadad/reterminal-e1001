# AGENTS.md

Instructions for AI agents working with this repository.

## What This Is

reTerminal E1001 is a 7.5" ePaper display connected to the local network. It shows a 4-page carousel of information (market data, clock, GitHub, status) that can be navigated with physical buttons or controlled via HTTP API.

## Device Details

- **IP:** 192.168.7.77
- **Display:** 800x480 monochrome ePaper
- **Refresh:** ~3 seconds (slow - minimize updates)

## Common Tasks

### Refresh a Page

```bash
cd ~/Desktop/base/reterminal-e1001
./refresh.sh market   # or: clock, github, status, all
```

### Check Device Status

```bash
curl -s http://192.168.7.77/status | jq .
```

### Push Custom Text

```bash
cd ~/Desktop/base/reterminal-e1001
source .venv/bin/activate
python python/reterminal.py --host 192.168.7.77 --text "Hello" --page 0
```

### Navigate Pages

```bash
# Next page
curl -X POST -H "Content-Type: application/json" \
  -d '{"action":"next"}' http://192.168.7.77/page

# Specific page
curl -X POST -H "Content-Type: application/json" \
  -d '{"page":0}' http://192.168.7.77/page
```

## Page Assignments

| Page | Name | Content |
|------|------|---------|
| 0 | market | VIX, S&P 500, Dow Jones |
| 1 | clock | Time and date |
| 2 | github | GitHub activity |
| 3 | status | System status |

## Adding Content

To add a new page type:
1. Create `python/pages/newpage.py` (see CLAUDE.md for template)
2. Add to `PAGES` dict in `python/refresh.py`
3. Run `./refresh.sh newpage` to test

## Important Notes

- **Minimize refreshes** - ePaper flickers on update; don't refresh frequently
- **White background** - Use `color=1` for background, `fill=0` for black text
- **Bitmap encoding** - Set bit = black pixel (GxEPD2 convention)
- **Market data** - Requires Schwab auth in agent-alpha project
- **Virtual env** - Always `source .venv/bin/activate` before running Python

## Firmware Updates

```bash
cd ~/Desktop/base/reterminal-e1001/firmware
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
- Testing (use `/status` or `/beep` instead)
- Multiple rapid updates

## Integration Points

- **Clawdbot:** Skill at `~/Desktop/base/clawdbot/skills/reterminal/`
- **Telegram:** Can trigger via clawdbot min bot
- **Cron:** Auto-refresh at 6:30 AM and 1:00 PM PT (Mon-Fri)
