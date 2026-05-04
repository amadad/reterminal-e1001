# Kitchen Display SOP

This repo can run a four-slot kitchen display from local markdown files. The
main operational risk is accidentally running multiple publishers that disagree
about slot ownership.

## Current slot ownership

The public example manifest uses `~/reterminal-content/family/` as the content
root. Keep machine-specific paths in `python/examples/kitchen-display.local.json`
(or set `RETERMINAL_FEED`) rather than editing public examples with private
paths.

| Slot | Live page | Example source | Provider |
| --- | --- | --- | --- |
| 0 | Today / Tomorrow agenda | `~/reterminal-content/family/calendar.md` | `python/reterminal/providers/calendar.py` |
| 1 | Missions | `~/reterminal-content/family/missions.md` | `python/reterminal/providers/missions.py` |
| 2 | Upcoming events | `~/reterminal-content/family/events.md` | `python/reterminal/providers/events.py` |
| 3 | Activities / movies | `~/reterminal-content/family/activities.md` | `python/reterminal/providers/activities.py` |

All four slots are markdown-backed. Slot pins live in the provider manifest
(`slot: 0..3`) rather than in provider code. The public manifest is
`python/examples/kitchen-display.json`; machine-specific paths belong in the
ignored `python/examples/kitchen-display.local.json`.

Legacy scenes named `ready-board`, `need-board`, `reset-board`, and older
fixed-page JSON feeds are not live slot owners.

## Safe refresh rule

Production refresh should be owned by one watcher:

```bash
cd python
uv run reterminal publish --feed examples/kitchen-display.json --push --watch --live
```

For local production, prefer an ignored manifest:

```bash
cp python/examples/kitchen-display.json python/examples/kitchen-display.local.json
# edit paths locally
RETERMINAL_FEED=python/examples/kitchen-display.local.json \
  scripts/reterminal-publish-watch.sh
```

The wrapper discovers the current DHCP-assigned host unless `RETERMINAL_HOST` is
explicitly set. If no host is reachable at startup, it waits and retries instead
of crash-looping. Discovery and device HTTP operations fall back to `curl` when
Python `requests` cannot open the route. During `publish --watch`, connection
failures are logged as compact warnings; the live loop attempts rediscovery and
retries the upload without marking a slot current until the push succeeds.

The loop watches the markdown files via FSEvents and re-renders + pushes only
the slots whose bitmap changed. It preserves the current visible slot unless an
operator explicitly selects one.

If you change slot ownership, update all of these in the same change:

1. `CLAUDE.md` live-feed architecture section
2. this SOP
3. the provider manifest
4. content-file conventions, if the file/section format changes
5. a verification note with device readback hashes, if you tested live hardware

## Launchd example

A public-safe template lives at `scripts/sh.reterminal.publish.example.plist`.
Copy it to `~/Library/LaunchAgents/sh.reterminal.publish.plist`, replace paths
with your local checkout, and keep the installed/local plist out of git.

## Firmware/version checklist

When checking whether the physical unit is current, prefer firmware-reported
provenance over memory:

```bash
env -u VIRTUAL_ENV uv --directory python run reterminal capabilities --host <device-ip>
env -u VIRTUAL_ENV uv --directory python run reterminal doctor --host <device-ip> --feed python/examples/kitchen-display.json
```

`capabilities` should show firmware version, build SHA, build time, reset
reason, reconnect counters, and uptime. `doctor` compares the firmware build SHA
against the current checkout when both are available; if the build SHA is
`unknown`, treat firmware currency as unverified.

## Recovery checklist

When the display shows stale or unexpected content, do this in order:

1. Confirm only one watcher/publisher is running.
2. If the device is not reachable, inspect USB serial logs first. USB proves the
   board is alive; HTTP over Wi-Fi is still required for slot updates.
3. Confirm the watcher uses the intended manifest (`RETERMINAL_FEED` or the
   default `examples/kitchen-display.local.json`/`examples/kitchen-display.json`).
4. Touch the markdown sources named by the active manifest to force a refresh. For the public example:
   ```bash
   touch ~/reterminal-content/family/{calendar,missions,events,activities}.md
   ```
5. If the watcher is broken, run a one-shot publish instead of starting another
   loop:
   ```bash
   cd python
   uv run reterminal publish --feed examples/kitchen-display.json --push --live
   ```
6. Verify device readback for slots 0-3:
   ```bash
   for slot in 0 1 2 3; do
     curl -fsS "http://$HOST/snapshot?page=$slot" -o "/tmp/reterminal-slot-$slot-live.raw"
     shasum -a 256 "/tmp/reterminal-slot-$slot-live.raw"
   done
   ```
7. Select the requested visible slot:
   ```bash
   curl -fsS -X POST "http://$HOST/page" \
     -H 'Content-Type: application/json' \
     -d '{"page":1,"full":true}'
   ```

## Crash / freeze investigation rule

Do not conflate content regression with firmware crashes.

- If the device is reachable and `/snapshot` hashes match, the issue is content
  ownership or navigation state.
- If the device disappears from discovery, ping, and `/status`, investigate
  firmware/Wi-Fi/display refresh stability from USB serial logs.
- Avoid `clear --all` unless a blank/wipe is intended. Prefer regenerate →
  upload → show current slot.

Call the freeze issue resolved for a physical unit only after a 48–72h soak with
no manual power cycle, reachable `/status`, increasing uptime except intentional
or firmware self-recovery reboots, no panic reset reason, and watcher logs
showing retry/recovery rather than repeated tracebacks. If a self-recovery
reboot occurs, `/capabilities` should report `last_self_restart_reason` so the
event is attributed instead of guessed from the stale ePaper image.
