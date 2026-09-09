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

- tracked firmware is a deep-sleep HTTP client: timer wakes fetch `/content-hash`, download changed `/content/slot-N` bitmaps, persist them, refresh, then sleep
- the display contract is `800x480`, `1-bit`, `48000` bytes per raw image
- firmware allocates **4** physical slots with neutral names `slot-0..slot-3`
- a 3-second right-button hold opens a 10-minute diagnostic window exposing `/status`, `/eventlog`, `/snapshot`, `/imageraw`, `/page`, and `/sleep`
- slots persist to LittleFS across normal power cycles; a failed slot write must preserve its previous bytes and full SHA-256
- on boot, firmware restores persisted slots and shows the last active page
- display uses **full refresh on every path**. Partial refresh produced layered artifacts between dissimilar pages; every refresh calls `display.hibernate()`
- short button wakes navigate cached pages without postponing the polling deadline; timer wakes and diagnostic long holds pull fresh content
- USB interrogation identified the board as `ESP32-S3` with embedded `8MB` PSRAM and `32MB` flash behind a `CH340` serial bridge

The checked-in `artifacts/probe-report.json` is sanitized evidence for the
4-slot hardware and the pre-pull firmware. It predates the tracked deep-sleep
refactor; reflash and regenerate it before treating the current contract as
physically verified.

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
│       ├── family/              # PIL-free parsers/projections plus explicit calendar acquisition
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
6. **Use the bundled Atkinson Hyperlegible fonts for ePaper rendering.** Do not depend on host system fonts; identical inputs must produce identical pixels on macOS and Linux.
   - Rules 6–9 are the rendering *constraints*. The *design system* — type ladder, spacing, slot anatomy, shared `draw_kicker`/`draw_rule`/`shape_for` — lives in `docs/design.md` (intent) and `python/reterminal/render/kitchen.py` (tokens). Renderers compose from those tokens, not ad hoc `font(n)`/margins; snapshot goldens pin the result. Read `docs/design.md` before restyling a slot.
7. **Text-heavy scenes should render with a hard black/white threshold; reserve Floyd-Steinberg dithering for poster/image scenes.** That keeps body copy from turning into dot-matrix texture.
8. **Always set `draw.fontmode = "1"` immediately after every `ImageDraw.Draw()` call.** Pillow's default (`"L"`) antialiases text into sub-pixel greyscale; after 1-bit thresholding that becomes dot-matrix noise. Every render and provider site in the codebase sets this — new sites must too.
9. **Full refresh on every path.** Push, navigation, manual button, boot — all full. Partial refresh is a poor fit for this display because the 4 slots hold dissimilar content (different layouts, not incremental page turns), and the panel's partial LUT produces layered artifacts when pixel deltas are large. The 2-second flash on nav is the accepted cost. Call `display.hibernate()` after every refresh. (This codebase does not expose a partial-refresh path; re-introducing one would need a very specific use case — incremental updates to the same layout, e.g. a ticking clock in a fixed position.)

## Live feed architecture

The everyday kitchen edition uses **three calendar pages plus a current Quest or Tomorrow fallback**, watched via FSEvents by `reterminal publish --watch`. Machine-specific source paths and live slot ownership belong in the ignored `python/examples/kitchen-display.local.json`; `python/examples/kitchen-calendar.json` defines the everyday edition, while `kitchen-display.json` remains a mixed-provider compatibility example. Rendering reads local sources without requiring calendar/chat/cloud APIs. The explicit `calendar-export` command acquires a structured Google Calendar projection through the installed gws CLI; markdown projections remain supported.

```
Google Family Calendar exporter ─►  manifest-selected calendar.md or calendar JSON
                                                        │
                                                        ▼  (FSEvents on all sources)
                                       reterminal publish --watch
                                                        │
                                                        ▼
                              host content API on :8765 (/content-hash, /content/slot-N)
                                                        │
                                                        ▼
                                  deep-sleeping device pulls on its next wake
```

Everyday edition (check the local manifest for actual activation):

- **slot 0**: `calendar`, `view: now` (the default) — today/tomorrow. Absolute-date sections distinguish missing data from no scheduled events.
- **slot 1**: `calendar`, `view: week` — first event on up to four scheduled days within the next week, with counts for extra events.
- **slot 2**: optional current `quest`, falling back to `calendar`, `view: prepare` — tomorrow's first event and its recorded location. Missing, invalid, and expired quests yield their slot automatically.
- **slot 3**: `calendar`, `view: weekend` — Saturday/Sunday plans, advancing on Monday.

The calendar exporter runs every 20 minutes as system LaunchDaemon `sh.reterminal.family-calendar`; the continuous publisher is `sh.reterminal.publish` in the same system domain. Use `launchctl print system/<label>` for current state and `sudo launchctl kickstart -k system/sh.reterminal.publish` after Python code changes. Manifest edits hot-reload configuration but cannot reload already-imported Python modules. No new cron is needed for these calendar views. Date selection lives in `family/agenda.py`, composition in `render/agenda.py`, and adapter wiring in `providers/calendar.py`.

The tracked public example still demonstrates `calendar` / `missions` / `comingup` / `camps`. Standalone `missions`, `events`, `activities`, and consolidated `comingup` providers remain registered and tested for other manifests.

The structured JSON exporter preserves full days, event ends, timezone, status, and
source check time; markdown remains supported. See `docs/calendar-source.md` for
the recurring job replacement. See `docs/delivery.md` for host-first firmware
rollout, receipts, and the three-timer-update physical gate. Never infer delivery
from server availability or optical success from a returned driver call.

The wiring lives in a provider manifest such as `python/examples/kitchen-display.json` (a provider manifest, not a scene list). Provider implementations are in `python/reterminal/providers/{calendar,missions,events,activities,comingup,camps,features}.py` — each owns a renderer + `SceneProvider` class. The established family grammars import parsers/dataclasses from `reterminal.family.<name>`; `features.py` instead reads only an explicit `## Kitchen Display` projection from an allowlisted wiki page so private surrounding prose cannot enter the scene model. The public `reterminal.family` parsing API remains PIL-free (markdown/JSON → dataclasses), so non-display consumers can `from reterminal.family import parse_calendar, parse_missions, ...` without the render pipeline. The separate `family/calendar_export.py` module performs explicit Google acquisition for `calendar-export`; parsers never call it. Each provider returns a `SceneSpec` carrying a prerendered 800x480 1-bit bitmap; `MonoRenderer` short-circuits on prerendered scenes and just blits.

Markdown sources can be linted with `reterminal lint --feed <manifest>`; `reterminal doctor --feed <manifest>` runs the same lint as part of standard health checks (use `--skip-lint` to opt out). Generated/local feeds surface a black `STALE` pill when file mtime is authoritative: calendar 2h, missions 3d, events/activities 14d. Canonical trip/quest/camps pages use explicit reviewed/valid-through content instead, so unrelated private-page edits do not change pixels.

Beyond the original markdown providers, `quest` and `trip` can take a slot by reading an explicit display-safe wiki block: `{"type": "quest"|"trip", "path": "<wiki-page>", "slot": N}`. Their 1-bit feature artwork is deterministic and snapshot-tested; they never invoke an image model at render time. A `photo` provider can also take any slot: `{"type": "photo", "path": "<folder>", "mode": "newest"|"daily", "slot": N}`. It Floyd-Steinberg dithers a chosen image full-bleed (with optional caption from a sidecar `.txt`); see `python/reterminal/providers/photos.py`. Curating the source folder matters more than the renderer — high-contrast portraits, line art, and B&W photography survive 1-bit rendering; phone snapshots and busy color images do not.

`reterminal brief --feed <manifest>` is a sample non-display consumer of `reterminal.family`: reads the manifest's calendar/missions/events/activities files and prints a daily readout. Useful as-is and as a worked example of what other tools (digests, recall CLIs, OC flows) can build on the family API.

The trigger loop (`python/reterminal/app/live.py`) uses `watchdog` for FSEvents on the parent directories of every source file the manifest names (a provider like `comingup` contributes more than one), plus the manifest file itself — editing the manifest hot-reloads providers in place, no restart. There is a 5-minute sanity tick. It atomically installs complete rendered editions in an in-memory cache and serves `GET /content-hash`, hash-bound `GET /content/slot-N`, `GET /health`, and `POST /receipt` on port 8765. Receipt history persists alongside the manifest; configuration errors remain visible until a successful reload. The firmware is the HTTP client; it wakes, compares hashes, fetches changed raw bitmaps, refreshes the panel, then sleeps. Slot pins live in the provider manifest (`slot: 0..3`), not in provider code. The public launchd template at `scripts/sh.reterminal.publish.example.plist` runs `scripts/reterminal-publish-watch.sh`.

Operational invariant: localhost health is not enough. The publisher must respond on the MacBook LAN IP because that is the path the device uses. If `curl http://127.0.0.1:8765/content-hash` works but `curl http://<macbook-lan-ip>:8765/content-hash` hangs, fix macOS Application Firewall for the Python runtime used by `uv`, then restart `sh.reterminal.publish`. The pull protocol is plain unauthenticated HTTP; run it only on a trusted LAN and use router/VLAN or host-firewall isolation rather than pretending the Python process is a security boundary.

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
uv run --with pip-audit pip-audit --skip-editable
```

Run all three checks locally before pushing. A known-vulnerable locked
dependency fails the dependency audit.

For live device work:

```bash
cd python
uv run reterminal discover
uv run reterminal doctor
uv run reterminal capabilities
uv run reterminal probe
```

Do not assume a prior DHCP lease is still valid.
