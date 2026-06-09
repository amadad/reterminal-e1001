# CLAUDE.md

Project guidance for working with this repository.

## Current product shape

This repo now treats the reTerminal as a **4-slot host-rendered display target**.

The architecture is:

- **device**: truthful host-side SDK for the current firmware contract
- **providers**: adapters that fetch logical content
- **scenes**: structured scene model
- **scheduler**: maps logical scenes into the 4 physical slots
- **render**: typography/layout/image pipeline for monochrome output
- **app**: publish previews or push scenes to the device

The older fixed-page modules have been removed; provider manifests are the active source of slot ownership.

## Verified hardware/firmware behavior

Based on live probing plus USB bootloader interrogation on a macOS host:

- device now connects over Wi-Fi and exposes `/status`, `/capabilities`, `/buttons`, `/beep`, `/page`, `/snapshot`, `/imageraw`, `/clear`
- current live contract is `800x480`, `1-bit`, `48000` bytes per raw image
- current firmware exposes **4** physical slots with neutral names `slot-0..slot-3`
- `snapshot_readback` is live and can return the exact stored raw bitmap for a loaded slot
- slots are persisted to LittleFS on the 32MB flash — survive power cycles and reboots
- on boot, firmware restores persisted slots and shows the last active page (no ready screen unless first boot)
- firmware sends a gratuitous ARP every 4 minutes (`ARP_KEEPALIVE_MS = 240000`) via `etharp_gratuitous()` on all up ETHARP interfaces. This keeps the router's ARP table entry for the device alive and prevents the "zombie WiFi" state (802.11 up, TCP dead) caused by ARP cache expiry on the router side.
- `WiFi.setAutoReconnect(true)` — driver manages reconnection. `maintainWifi()` monitors state and starts mDNS/OTA on restoration, but issues no manual `WiFi.disconnect()` / `WiFi.begin()` calls. A full restart fires after 10 min of sustained WiFi loss (`WIFI_SELF_RESTART_MS`).
- firmware performs an unconditional `ESP.restart()` after 12 hours of uptime (`PERIODIC_RESTART_MS = 43200000`) as a last-resort safety valve in case the LWIP stack itself corrupts. All slots survive via LittleFS. The threshold is overridable via `RETERMINAL_PERIODIC_RESTART_MS` in `platformio.local.ini`. `/capabilities` reports `periodic_restart_ms`, `arp_keepalive_ms`, `last_arp_ms`, and `last_self_restart_reason` (`periodic` | `wifi_stale` | `none`).
- display uses **full refresh on every path** — image push, navigation, manual button, boot restore. Partial refresh was tried for navigation but produced layered/ghosted artifacts because slot content is dissimilar (agenda vs list vs list vs list); the partial LUT can only handle small pixel deltas cleanly. The flash on every nav is the accepted cost. Every refresh function calls `display.hibernate()` at the end. See `docs/_solutions.md`
- `POST /page` does **not** beep — beep is reserved for physical button presses
- USB interrogation identified the board as `ESP32-S3` with embedded `8MB` PSRAM and `32MB` flash behind a `CH340` serial bridge

The checked-in `artifacts/probe-report.json` is current sanitized probe evidence from the reflashed firmware. It confirms clean invalid-slot rejection rather than the older wraparound/display-immediate behavior.

See:

- `docs/device-profile.md`
- `docs/hardware-verification.md`
- `artifacts/probe-report.json`

## Working structure

```text
reterminal-e1001/
├── firmware/
├── python/
│   ├── examples/                # sample scene feeds
│   ├── tests/
│   └── reterminal/
│       ├── app/
│       ├── cli/
│       ├── device/
│       ├── family/              # pure markdown parsers + dataclasses for the four kitchen files; PIL-free, importable by any non-display tool
│       ├── providers/
│       ├── render/              # mono renderer, layout/bitmap primitives, shared viz vocabulary (see docs/visualizations.md)
│       ├── scheduler/
│       ├── scenes/
│       ├── payloads.py
│       ├── protocols.py
│       └── probe.py
├── docs/
└── artifacts/
```

## Commands to prefer

```bash
cd python
uv run reterminal discover
uv run reterminal doctor                                                 # also lints manifest sources unless --skip-lint
uv run reterminal doctor --feed examples/kitchen-display.json            # connectivity + lint in one shot
uv run reterminal status
uv run reterminal capabilities
uv run reterminal snapshot --png ./current.png
uv run reterminal clear --all
uv run reterminal probe
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews --push --live
uv run reterminal publish --feed examples/kitchen-display.json --watch --live
uv run reterminal lint --feed examples/kitchen-display.json
uv run reterminal brief --feed examples/kitchen-display.json             # sample family-state consumer (today/tomorrow/missions/next-event/queue)
```

## Agent access quickstart

Read `docs/access.md` before debugging connectivity or Python-path problems.

Key rules:

- The Python project root is `python/`, not the repo root. From repo root, use `env -u VIRTUAL_ENV uv --directory python run reterminal ...`; from `python/`, use `env -u VIRTUAL_ENV uv run reterminal ...`.
- USB serial is for boot logs, bootloader interrogation, and PlatformIO flashing. Slot status, snapshots, uploads, and page selection are HTTP-over-Wi-Fi operations.
- Use `pio device list` to find current `/dev/cu.usbserial-*` or `/dev/cu.usbmodem*` paths. Numeric suffixes drift with USB topology.
- If USB logs are visible but `reterminal discover` returns no hosts, the device is alive over USB but not reachable over Wi-Fi/HTTP; diagnose Wi-Fi from serial logs instead of guessing old DHCP leases.
- On some macOS networks, Python `requests` reports `No route to host` even when `curl` works. The CLI has curl fallback for live device HTTP; prefer CLI/curl over ad hoc `requests` snippets.

## Decommissioned legacy commands

The old fixed-page `refresh` / `watch` CLI commands and `reterminal/pages/*` modules are gone. Do not use `./refresh.sh market`; it now points users to the provider-driven publish flow.

## Architectural rules

1. **Do not assume more than 4 physical slots** unless firmware changes and the probe is updated.
2. **Do not put Paperclip-specific logic in firmware or the device SDK.** Add it as a provider.
3. **Do not tie scene meaning to slot numbers.** Slots are physical; scenes are logical.
4. **Prefer provider/scene/scheduler/render boundaries** over page-specific scripts.
5. **Use `reterminal/device` for capability-aware slot operations** instead of hitting raw firmware semantics from new code.
6. **Use Helvetica (not Helvetica Neue) for ePaper rendering.** Uniform stroke weight survives 1-bit rendering on this panel better than thinner neo-grotesque variants. See `_solutions.md` for the Neue regression.
   - Rules 6–9 are the rendering *constraints*. The *design system* — type ladder, spacing, slot anatomy, shared `draw_kicker`/`draw_rule`/`shape_for` — lives in `docs/design.md` (intent) and `python/reterminal/render/kitchen.py` (tokens). Renderers compose from those tokens, not ad hoc `font(n)`/margins; snapshot goldens pin the result. Read `docs/design.md` before restyling a slot.
7. **Text-heavy scenes should render with a hard black/white threshold; reserve Floyd-Steinberg dithering for poster/image scenes.** That keeps body copy from turning into dot-matrix texture.
8. **Always set `draw.fontmode = "1"` immediately after every `ImageDraw.Draw()` call.** Pillow's default (`"L"`) antialiases text into sub-pixel greyscale; after 1-bit thresholding that becomes dot-matrix noise. Every render and provider site in the codebase sets this — new sites must too.
9. **Full refresh on every path.** Push, navigation, manual button, boot — all full. Partial refresh is a poor fit for this display because the 4 slots hold dissimilar content (different layouts, not incremental page turns), and the panel's partial LUT produces layered artifacts when pixel deltas are large. The 2-second flash on nav is the accepted cost. Call `display.hibernate()` after every refresh. (This codebase does not expose a partial-refresh path; re-introducing one would need a very specific use case — incremental updates to the same layout, e.g. a ticking clock in a fixed position.)

## Live feed architecture

The kitchen display is driven by **four local markdown files**, watched via FSEvents by `reterminal publish --watch`. The public example uses `~/reterminal-content/family/`; machine-specific paths belong in an ignored local manifest such as `python/examples/kitchen-display.local.json`. The display pipeline has zero required calendar/chat/cloud API dependencies: external systems such as Google Calendar feed markdown upstream of this repo.

```
OpenClaw/calendar exporter ─►  ~/reterminal-content/family/calendar.md
OpenClaw/local editors     ─►  ~/reterminal-content/family/missions.md
OpenClaw/local editors     ─►  ~/reterminal-content/family/events.md
OpenClaw/local editors     ─►  ~/reterminal-content/family/activities.md
                                                   │
                                                   ▼  (FSEvents on all 4 paths)
                                  reterminal publish --watch
                                                   │
                                                   ▼
                         host content API on :8765 (/content-hash, /content/slot-N)
                                                   │
                                                   ▼
                             deep-sleeping device pulls on its next wake
```

4-slot layout, one provider per slot:

- **slot 0**: `calendar` — today/tomorrow agenda from `calendar.md`. Sections are absolute dates (`## 2026-05-08 Fri`); the renderer picks today/tomorrow at render time from `date.today()`. Retired `## Today` / `## Tomorrow` headers trigger a migration notice. See `docs/oc-calendar-heartbeat.md`.
- **slot 1**: `missions` — mission cards from `missions.md`
- **slot 2**: `comingup` — one forward-looking "Coming Up" board merging upcoming events (`events.md` `## Upcoming`) with the activities queue (`activities.md` `## Queue`). The backward-looking `## Recent` log is deliberately not shown. Config names two sources: `{"type": "comingup", "events": "…/events.md", "queue": "…/activities.md", "slot": 2}`.
- **slot 3**: `camps` — week-by-week summer grid parsed from a markdown table (e.g. the Madad Wiki `family-summer-2026-camps.md`). Renders week / boys / Laila; the source's Notes/cost column is dropped and never shown on the shared wall.

The standalone `events` and `activities` providers still exist (registered, tested) for layouts that want them separately, but the shipped kitchen layout consolidates them into `comingup`.

The wiring lives in a provider manifest such as `python/examples/kitchen-display.json` (a provider manifest, not a scene list). Provider implementations are in `python/reterminal/providers/{calendar,missions,events,activities,comingup,camps}.py` — each owns a renderer + `SceneProvider` class and imports its parser/dataclasses from `reterminal.family.<name>`. The `reterminal.family` package is the pure parsing layer (markdown → dataclasses, no PIL) so non-display consumers (briefs, OC flows, recall CLIs) can `from reterminal.family import parse_calendar, parse_missions, ...` without dragging in the render pipeline. Each provider returns a `SceneSpec` carrying a prerendered 800x480 1-bit bitmap; `MonoRenderer` short-circuits on prerendered scenes and just blits.

Markdown sources can be linted with `reterminal lint --feed <manifest>`; `reterminal doctor --feed <manifest>` runs the same lint as part of standard health checks (use `--skip-lint` to opt out). Renderers also surface a black `STALE` pill in the bottom-right corner when a source file's mtime exceeds a per-provider threshold (calendar 2h, missions 3d, events/activities 14d) — converts a dead upstream writer into a visible kitchen signal instead of a quietly frozen display.

Beyond the four markdown providers, an additional `photo` provider type can take any of the four physical slots: `{"type": "photo", "path": "<folder>", "mode": "newest"|"daily", "slot": N}`. It Floyd-Steinberg dithers a chosen image full-bleed (with optional caption from a sidecar `.txt`); see `python/reterminal/providers/photos.py`. Curating the source folder matters more than the renderer — high-contrast portraits, line art, and B&W photography survive 1-bit rendering; phone snapshots and busy color images do not.

`reterminal brief --feed <manifest>` is a sample non-display consumer of `reterminal.family`: reads the manifest's calendar/missions/events/activities files and prints a daily readout. Useful as-is and as a worked example of what other tools (digests, recall CLIs, OC flows) can build on the family API.

The trigger loop (`python/reterminal/app/live.py`) uses `watchdog` for FSEvents on the parent directories of every source file the manifest names (a provider like `comingup` contributes more than one), plus the manifest file itself — editing the manifest hot-reloads providers in place, no restart. There is a 5-minute sanity tick. It renders changed slots into an in-memory cache and serves `GET /content-hash` plus `GET /content/slot-N` on port 8765. The firmware is the HTTP client; it wakes, compares hashes, fetches changed raw bitmaps, refreshes the panel, then sleeps. Slot pins live in the provider manifest (`slot: 0..3`), not in provider code. The public launchd template at `scripts/sh.reterminal.publish.example.plist` runs `scripts/reterminal-publish-watch.sh`.

Operational invariant: localhost health is not enough. The publisher must respond on the MacBook LAN IP because that is the path the device uses. If `curl http://127.0.0.1:8765/content-hash` works but `curl http://<macbook-lan-ip>:8765/content-hash` hangs, fix macOS Application Firewall for the Python runtime used by `uv`, then restart `sh.reterminal.publish`.

Do **not** reintroduce legacy `ready-board` / `need-board` / `reset-board` as live slots unless explicitly asked for a rollback.

For the kitchen display, prefer low-churn, action-oriented layouts over live clocks or dense dashboard chrome so hidden-slot updates do not cause unnecessary visible refreshes. The SOP for changing live slot ownership is in `docs/kitchen-display-sop.md`.

## Design direction

- provider adapters for Paperclip and other markdown sources beyond the family folder
- stronger typography and layout templates, especially action-oriented agenda/list compositions with sparse chrome
- monochrome poster/media pipeline
- scheduler strategies for pinned + rotating scenes (only if a real need shows up — current 4-slot pinned mapping is intentional)

## Verification

For code changes:

```bash
cd python
uv run --extra dev pytest -q
uv run --extra dev ruff check reterminal tests
```

CI runs the same tests and lint on a 3.10/3.12/3.13 matrix plus `pip-audit`
(`uv run --with pip-audit pip-audit --skip-editable`) — a known-vulnerable
locked dependency fails the build, not just local sweeps.

For live device work:

```bash
cd python
uv run reterminal discover
uv run reterminal doctor
uv run reterminal capabilities
uv run reterminal clear --all
uv run reterminal probe
```

Do not assume a prior DHCP lease is still valid.
