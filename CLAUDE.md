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

The older fixed-page modules remain for compatibility, but they are no longer the primary design center.

## Verified hardware/firmware behavior

Based on live probing plus USB bootloader interrogation on `kunst`:

- device now connects over Wi-Fi and exposes `/status`, `/capabilities`, `/buttons`, `/beep`, `/page`, `/snapshot`, `/imageraw`, `/clear`
- current live contract is `800x480`, `1-bit`, `48000` bytes per raw image
- current firmware exposes **4** physical slots with neutral names `slot-0..slot-3`
- `snapshot_readback` is live and can return the exact stored raw bitmap for a loaded slot
- slots are persisted to LittleFS on the 32MB flash — survive power cycles and reboots
- on boot, firmware restores persisted slots and shows the last active page (no ready screen unless first boot)
- display uses **full refresh on every path** — image push, navigation, manual button, boot restore. Partial refresh was tried for navigation but produced layered/ghosted artifacts because slot content is dissimilar (agenda vs list vs list vs list); the partial LUT can only handle small pixel deltas cleanly. The flash on every nav is the accepted cost. Every refresh function calls `display.hibernate()` at the end. See `docs/_solutions.md`
- `POST /page` does **not** beep — beep is reserved for physical button presses
- USB interrogation identified the board as `ESP32-S3` with embedded `8MB` PSRAM and `32MB` flash behind a `CH340` serial bridge on `kunst`

The checked-in `artifacts/probe-report.json` captures the older pre-reflash firmware's invalid-input behavior. Do not assume those old wraparound semantics are still live truth until the reflashed firmware is probed again.

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
│       ├── pages/               # legacy fixed-page modules
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

## Commands considered legacy

```bash
uv run reterminal refresh market
uv run reterminal watch clock -i 60
./refresh.sh market
```

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

The kitchen display is driven by **four markdown files in `~/madad/family/`**, watched via FSEvents by `reterminal publish --watch`. The display pipeline has zero API dependencies — no Google, no Discord, no OpenClaw.

```
Discord       ─►  orb        ─►  ~/madad/family/missions.md
Discord       ─►  orb        ─►  ~/madad/family/events.md
Discord       ─►  orb        ─►  ~/madad/family/activities.md
OC heartbeat  ─►  gws        ─►  ~/madad/family/calendar.md
                                          │
                                          ▼  (FSEvents on all 4 paths)
                          reterminal publish --watch  (launchd-supervised)
                                          │
                                          ▼
                                       device
```

4-slot layout, one provider per slot:

- **slot 0**: `calendar` — today/tomorrow agenda from `calendar.md` (machine-written by OC heartbeat)
- **slot 1**: `missions` — four-kid mission cards from `missions.md`
- **slot 2**: `events` — upcoming events from `events.md`
- **slot 3**: `activities` — recent + queued activities from `activities.md`

The wiring lives in `python/examples/kitchen-display.json` (a provider manifest, not a scene list). `~/madad/family/CONVENTIONS.md` documents the file-format contracts (preamble, renderer-consumed sections, `## Notes` working-memory). Provider implementations are in `python/reterminal/providers/{calendar,missions,events,activities}.py`. Each returns a `SceneSpec` carrying a prerendered 800x480 1-bit bitmap; `MonoRenderer` short-circuits on prerendered scenes and just blits.

The trigger loop (`python/reterminal/app/live.py`) uses `watchdog` for FSEvents on the parent directories of the four files, with a 5-minute sanity tick. An in-memory bitmap cache means the device only receives a `POST /imageraw` when the rendered output actually changes — no SHA cache on disk. The launchd plist at `scripts/sh.reterminal.publish.plist` keeps the loop alive across reboots.

Do **not** reintroduce legacy `ready-board` / `need-board` / `reset-board` as live slots unless Ali explicitly asks for a rollback. The legacy bash orchestrator (`~/oc-min/scripts/reterminal-{live,refresh}.sh`, `generate_reterminal_feed.py`) is no longer in the kitchen-display path; it remains in oc-min until the new pipeline has soaked.

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

Do not assume a prior DHCP lease is still valid. The recovered device later appeared at `.97` after earlier `.76/.77/.78` guesses failed.
