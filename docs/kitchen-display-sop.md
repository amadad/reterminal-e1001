# Kitchen Display SOP

This repo controls the reTerminal E1001 kitchen display. The expensive mistake
to avoid: accidentally overwriting the designed slots with older legacy feed
pages during the hourly refresh loop.

## Current slot ownership

| Slot | Live page | Source | Provider |
| --- | --- | --- | --- |
| 0 | Today / Tomorrow agenda | `~/madad/family/calendar.md` (machine-written by OC heartbeat from gws — see `docs/oc-calendar-heartbeat.md`) | `python/reterminal/providers/calendar.py` |
| 1 | Four-kid missions | `~/madad/family/missions.md` | `python/reterminal/providers/missions.py` |
| 2 | Upcoming events | `~/madad/family/events.md` | `python/reterminal/providers/events.py` |
| 3 | Activities / movies | `~/madad/family/activities.md` | `python/reterminal/providers/activities.py` |

All four slots are markdown-backed. The wiring lives in
`python/examples/kitchen-display.json` (a provider manifest). File-format
contracts are documented in `~/madad/family/CONVENTIONS.md`.

Legacy scenes named `ready-board`, `need-board`, `reset-board`, and the
old slot-0 `today-board` JSON path are not live slot owners.

## Safe refresh rule

Production refresh is owned by:

```bash
uv run reterminal publish --feed examples/kitchen-display.json --push --watch --live
```

This is launchd-supervised via `scripts/sh.reterminal.publish.plist`, which
runs `scripts/reterminal-publish-watch.sh`. The wrapper discovers the current
DHCP-assigned host unless `RETERMINAL_HOST` is explicitly set. The loop watches
the four markdown files via FSEvents and re-renders + pushes only the slots
whose bitmap actually changed. It preserves the current visible slot unless an
operator explicitly selects one. No legacy bash orchestrator, no tmux session.

If you change slot ownership, update all of these in the same change:

1. `CLAUDE.md` "Live feed architecture" section
2. this SOP
3. `python/examples/kitchen-display.json` (the manifest)
4. `~/madad/family/CONVENTIONS.md` if the file/section format changes
5. a verification note with readback hashes from the device

## Legacy fallback

The old fixed-page CLI `refresh` / `watch` commands are not live. If the new
pipeline misbehaves, prefer fixing or restarting the launchd watcher. Any
external fallback should be a one-shot deterministic push only — do not restart
a polling loop that can overwrite the designed slot ownership.

## Recovery checklist

When Ali says “old version,” “not refreshed,” or “where did the designed pages
go,” do this in order:

1. Confirm the watcher is running:
   ```bash
   launchctl list | grep sh.reterminal.publish
   tail -50 ~/Library/Logs/reterminal/publish.log
   ```
   If it is missing or crashed, reload:
   ```bash
   launchctl unload ~/Library/LaunchAgents/sh.reterminal.publish.plist
   launchctl load   ~/Library/LaunchAgents/sh.reterminal.publish.plist
   ```
2. Touch each markdown to force a refresh:
   ```bash
   touch ~/madad/family/{calendar,missions,events,activities}.md
   ```
   The watcher should react within ~1s and push any changed slots.
3. If the watcher is broken, fall back to a one-shot legacy push:
   ```bash
   ~/oc-min/scripts/reterminal-refresh.sh
   ```
   Single deterministic push, no loop. Then fix the watcher.
4. Verify device readback for slots 1-3 matches what the providers render:
   ```bash
   for slot in 0 1 2 3; do
     curl -fsS "http://$HOST/snapshot?page=$slot" -o "/tmp/reterminal-slot-$slot-live.raw"
     shasum -a 256 "/tmp/reterminal-slot-$slot-live.raw"
   done
   ```
5. Put the device on the page Ali is asking about:
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
  firmware/Wi-Fi/display refresh stability.
- Avoid `clear --all` unless Ali explicitly wants a blank/wipe. Prefer
  regenerate → upload → show current slot.
