# Kitchen Display SOP

This repo runs a four-slot kitchen display from allowlisted local markdown
sources. In the current architecture the reTerminal is a deep-sleeping HTTP
client: the always-on MacBook renders markdown into raw slot bitmaps and serves
them over HTTP; the device wakes, pulls changed slots, refreshes the panel, then
sleeps.

The main operational risks are:

- treating "publisher process is running" as proof the LAN content server works
- accidentally running multiple publishers that disagree about slot ownership
- manually maintaining source files that OpenClaw should generate

## Everyday slot ownership

Keep machine-specific paths in `python/examples/kitchen-display.local.json`
(or set `RETERMINAL_FEED`) rather than editing public examples with private
paths. The ignored local manifest owns the active household edition; the tracked
`python/examples/kitchen-display.json` remains a public compatibility/example
manifest.

| Slot | Everyday edition page | Source | Provider |
| --- | --- | --- | --- |
| 0 | Now: today + tomorrow | `~/reterminal-content/family/calendar.md` | `python/reterminal/providers/calendar.py` |
| 1 | Week: first event on up to four scheduled days within the next week, with additional-event counts | same calendar | `calendar`, `view: week` |
| 2 | Current Quest, or tomorrow's first event and recorded location | optional `quest.md`, calendar fallback | `quest` with `calendar`, `view: prepare` fallback |
| 3 | Weekend: Saturday/Sunday plans | same calendar | `calendar`, `view: weekend` |

The everyday edition is `python/examples/kitchen-calendar.json`; the installed
local manifest remains the authority for what is actually live. Preview this
edition before copying it to the local manifest. New Python code requires a
publisher restart; manifest edits alone hot-reload configuration, not modules.

Calendar views share one generated source and the existing scheduler. The
[structured exporter](calendar-source.md) replaces the old writer in the same
20-minute job, retaining complete days, end times, timezone, status, and locations.
Point local calendar paths at its JSON destination on activation; the example's
markdown source is still supported. Week advances daily, Weekend on Monday, and
Today retains ongoing events while dropping those with known elapsed end times.
Missing dates mean unavailable data. Calendar pages show a readable source-check
timestamp and STALE after two hours; rendering never renews that timestamp.
See [delivery verification](delivery.md) for receipts and the physical rollout gate.

The former summer edition (camps, Yellowstone, expired quest) is retired from
everyday use. Seasonal providers remain available for deliberately maintained
manifests. Slot pins live in the manifest (`slot: 0..3`), never in provider code.

The public example still demonstrates `calendar`, `missions`, `comingup`, and
`camps`. `comingup` merges upcoming dated events with the activities queue;
standalone `missions.py`, `events.py`, and `activities.py` remain registered for
other manifests. Legacy content files are not live merely because they still
exist on disk.

Legacy scenes named `ready-board`, `need-board`, `reset-board`, and older
fixed-page JSON feeds are not live slot owners.

## Source ownership

Each file is either a generated projection or an allowlisted projection of a
canonical source; ownership must stay explicit.

- The calendar source is generated from the Google Family Calendar every 20 minutes by
  launchd job `sh.reterminal.family-calendar`, with a 21-day window. Before migration
  this is the external markdown exporter; after migration the repo-owned exporter
  writes structured JSON covering today and the following 20 days. Humans
  should not maintain it manually. On the current Mac this is a system
  LaunchDaemon, running as the operator, with its last exit code visible via
  `launchctl print system/sh.reterminal.family-calendar`.
- The camps provider reads the first three columns of matching schedule-table
  rows from the canonical camps page and drops every later column before
  rendering.
- The trip and quest providers read only explicit `## Kitchen Display` blocks
  from canonical wiki pages. Keep booking, health, school, identity, and other
  private prose outside those blocks.
- Failed upstream fetches should leave the last-good source in place. Do not
  replace a good file with an auth error, empty export, or diagnostic text.

After source content is written as markdown or JSON, every slot follows the same downstream
path: file write -> FSEvents -> render cache -> publisher HTTP API -> device
pull on next wake.

## Safe refresh rule

Production refresh should be owned by one publisher. For the active local
edition, run the ignored manifest from `python/`:

```bash
cd python
uv run reterminal publish --feed examples/kitchen-display.local.json --watch --live
```

To create a machine-local manifest from the public example:

```bash
cp python/examples/kitchen-display.json python/examples/kitchen-display.local.json
# edit paths locally
RETERMINAL_FEED=python/examples/kitchen-display.local.json \
  scripts/reterminal-publish-watch.sh
```

The wrapper does not need the device IP in pull mode. The device knows the
publisher host IP and polls it while awake.

The loop watches markdown files via FSEvents and re-renders only slots whose
bitmap changed. It serves:

```text
GET /content-hash       -> JSON {"hashes": {"slot-0": "<sha256>", ...}}
GET /content/slot-N     -> 48000-byte raw 1-bit bitmap
```

The physical panel updates on the next device wake cycle, not immediately when
the file is written. Diagnostic/manual push paths are repair tools, not the
normal update path.

If you change slot ownership, update all of these in the same change:

1. `CLAUDE.md` live-feed architecture section
2. this SOP
3. the provider manifest
4. content-file conventions, if the file/section format changes
5. a verification note with device readback hashes, if you tested live hardware

## Launchd ownership and cadence

On the current Mac, both jobs live under `/Library/LaunchDaemons/`, not the
old `~/Library/LaunchAgents/` location. Verify the installed domain before
restarting; the archived agent plists do not establish runtime ownership.

```bash
launchctl print system/sh.reterminal.family-calendar
launchctl print system/sh.reterminal.publish
sudo launchctl kickstart -k system/sh.reterminal.publish
```

The publisher has KeepAlive and RunAtLoad; the exporter has RunAtLoad and a
1200-second interval. These run without an interactive login. The host must
remain awake and reachable on the LAN. The publisher reacts to file writes
and also recomputes time-relative views every five minutes. The panel pulls
on its next wake (about 30 minutes by default): allow roughly 55 minutes from
a calendar edit to its scheduled appearance on the panel. Changing this host
cadence does not change the firmware's wake interval.

The template below is an alternative per-user installation. Do not install it
alongside the existing system publisher.

A public-safe template lives at `scripts/sh.reterminal.publish.example.plist`.
Copy it to `~/Library/LaunchAgents/sh.reterminal.publish.plist`, replace paths
with your local checkout, and keep the installed/local plist out of git.

On macOS, the Application Firewall must allow incoming connections for the
Python runtime used by the publisher. If localhost works but the LAN IP hangs,
the device cannot pull even though launchd and `lsof` make the service look
alive.

Known symptom from 2026-05-21:

```bash
curl http://127.0.0.1:8765/content-hash        # works
curl http://<macbook-lan-ip>:8765/content-hash # connects then times out
```

Fix by allowing/unblocking the Python app that `uv` is running, then restart
the launchd service:

```bash
/usr/libexec/ApplicationFirewall/socketfilterfw --add /path/to/Python.app
/usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp /path/to/Python.app
sudo launchctl kickstart -k system/sh.reterminal.publish
```

For the current Kunst/Homebrew Python install, the path observed on 2026-05-21
was:

```text
/usr/local/Cellar/python@3.13/3.13.13_1/Frameworks/Python.framework/Versions/3.13/Resources/Python.app
```

## Firmware/version checklist

Enter the 10-minute diagnostic window with a 3-second right-button hold, then
prefer firmware-reported provenance over memory:

```bash
env -u VIRTUAL_ENV uv --directory python run reterminal capabilities --host <device-ip>
env -u VIRTUAL_ENV uv --directory python run reterminal doctor --host <device-ip> --feed python/examples/kitchen-display.json
```

`capabilities` is a host-derived view of diagnostic `/status`; it should show
firmware version, build SHA, build time, reset reason, slot state, battery, and
uptime. `doctor` compares the build SHA against the checkout when both are
available; if it is `unknown`, treat firmware currency as unverified.

## Recovery checklist

When the display shows stale or unexpected content, do this in order:

0. **Look at the slot first.** A black `STALE` pill means a generated/local upstream writer is dead, not the display. Fix the writer, not the publisher. Calendar is the most common offender (2h threshold); missions use 3d and events/activities 14d. Canonical trip/quest/camps pages use explicit header validity instead of filesystem mtime.
1. Confirm only one watcher/publisher is running.
2. Confirm the publisher serves both localhost and LAN:
   ```bash
   curl -fsS --max-time 3 http://127.0.0.1:8765/content-hash
   curl -fsS --max-time 3 http://<macbook-lan-ip>:8765/content-hash
   ```
   If localhost works and LAN hangs, fix macOS Application Firewall before
   touching the device.
3. Confirm the watcher uses the intended manifest (`RETERMINAL_FEED` or the
   default `examples/kitchen-display.local.json`/`examples/kitchen-display.json`).
4. Render the active manifest to a temporary preview and confirm its four slot assignments. Do not `touch` canonical sources merely to force a refresh; make a real source change or restart a stale publisher.
   ```bash
   env -u VIRTUAL_ENV uv --directory python run reterminal publish \
     --feed examples/kitchen-display.local.json \
     --preview /tmp/reterminal-live-preview
   ```
5. If the watcher is broken, restart the launchd publisher instead of starting
   another loop:
   ```bash
   sudo launchctl kickstart -k system/sh.reterminal.publish
   ```
6. If you need physical device readback, put the device in diagnostic mode with
   a 3-second right-button long press, then inspect it during the 10-minute
   diagnostic window:
   ```bash
   env -u VIRTUAL_ENV uv --directory python run reterminal discover
   env -u VIRTUAL_ENV uv --directory python run reterminal snapshot --host <device-ip> --png /tmp/reterminal-current.png
   ```
7. Do not use old push flows for normal freshness. Use diagnostic/manual paths
   only to repair or inspect a physical unit that failed to pull.

## Crash / freeze investigation rule

Do not conflate content regression with firmware crashes.

- If the publisher is unreachable on the MacBook LAN IP, fix the host serving
  layer first.
- If the publisher is reachable but the device does not pull on its next wake,
  investigate firmware Wi-Fi/client behavior from serial logs or diagnostic
  mode.
- Prefer regenerate → render → serve → wait for pull; there is no tracked
  firmware cache-clear endpoint.

Call a pull failure resolved only after several timer wake cycles complete
without a manual power cycle, the publisher remains reachable on its LAN IP,
and diagnostic `/eventlog` shows expected wake events rather than repeated
`wifi_fail` entries. Normal operation sleeps and exposes no `/status` endpoint,
so continuous HTTP uptime is not a valid soak criterion.
