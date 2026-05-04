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
uv run reterminal doctor
uv run reterminal status
uv run reterminal capabilities
uv run reterminal snapshot --png ./current.png
uv run reterminal clear --all
uv run reterminal probe
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews --push --live
uv run reterminal publish --feed examples/kitchen-display.json --push --watch --live
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
7. **Text-heavy scenes should render with a hard black/white threshold; reserve Floyd-Steinberg dithering for poster/image scenes.** That keeps body copy from turning into dot-matrix texture.
8. **Full refresh on every path.** Push, navigation, manual button, boot — all full. Partial refresh is a poor fit for this display because the 4 slots hold dissimilar content (different layouts, not incremental page turns), and the panel's partial LUT produces layered artifacts when pixel deltas are large. The 2-second flash on nav is the accepted cost. Call `display.hibernate()` after every refresh. (This codebase does not expose a partial-refresh path; re-introducing one would need a very specific use case — incremental updates to the same layout, e.g. a ticking clock in a fixed position.)

## Live feed architecture

The kitchen display can be driven by **four local markdown files**, watched via FSEvents by `reterminal publish --watch`. The public example uses `~/reterminal-content/family/`; machine-specific paths belong in an ignored local manifest such as `python/examples/kitchen-display.local.json`. The display pipeline has zero required calendar/chat/cloud API dependencies.

```
calendar exporter ─►  ~/reterminal-content/family/calendar.md
local editors     ─►  ~/reterminal-content/family/missions.md
local editors     ─►  ~/reterminal-content/family/events.md
local editors     ─►  ~/reterminal-content/family/activities.md
                                          │
                                          ▼  (FSEvents on all 4 paths)
                          reterminal publish --watch
                                          │
                                          ▼
                                       device
```

4-slot layout, one provider per slot:

- **slot 0**: `calendar` — today/tomorrow agenda from `calendar.md`
- **slot 1**: `missions` — mission cards from `missions.md`
- **slot 2**: `events` — upcoming events from `events.md`
- **slot 3**: `activities` — recent + queued activities from `activities.md`

The wiring lives in a provider manifest such as `python/examples/kitchen-display.json` (a provider manifest, not a scene list). Provider implementations are in `python/reterminal/providers/{calendar,missions,events,activities}.py`. Each returns a `SceneSpec` carrying a prerendered 800x480 1-bit bitmap; `MonoRenderer` short-circuits on prerendered scenes and just blits.

The trigger loop (`python/reterminal/app/live.py`) uses `watchdog` for FSEvents on the parent directories of the four files, with a 5-minute sanity tick. It seeds its in-memory slot hashes from `/snapshot` on startup, refreshes capabilities on each tick to detect device reboots/storage loss, then marks a slot current only after a successful upload; this keeps launchd restarts, reboots, and transient upload failures from causing redundant or missed pushes. Slot pins live in the provider manifest (`slot: 0..3`), not in provider code. The public launchd template at `scripts/sh.reterminal.publish.example.plist` runs `scripts/reterminal-publish-watch.sh`, which discovers the DHCP-assigned host unless `RETERMINAL_HOST` is explicitly set.

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
