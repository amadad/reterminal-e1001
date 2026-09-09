# Python package

The Python package is the active control plane for the reTerminal E1001.

It now has two layers:

- a **truthful device SDK** for the current 4-slot firmware contract
- a **scene publishing pipeline** for provider-driven monochrome layouts

## Device contract

Verified hardware plus current tracked source establish:

- 800x480 monochrome
- 48,000-byte raw upload payloads
- 4 physical slots
- current tracked firmware rejects invalid `page` requests with `400 Page out of range`
- current tracked firmware rejects invalid `imageraw?page=N` uploads with `400 Page out of range`
- tracked firmware persists loaded slots in LittleFS and operates as a deep-sleep HTTP pull client

Use `reterminal probe`, `reterminal capabilities`, and `reterminal doctor` before assuming anything else. During the 10-minute diagnostic window, `capabilities` derives the fixed display contract and live slot state from `/status`, while `snapshot` reads back an exact stored bitmap. `doctor` compares firmware build SHA to the checkout when possible. The HTTP client falls back to `curl` on macOS route failures where Python `requests` cannot reach a device that `curl` can.

## Install

If running from repo root, either `cd python` first or use `env -u VIRTUAL_ENV uv --directory python run ...`. See `../docs/access.md` for the full agent access contract.

```bash
uv sync
```

Or:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Core commands

```bash
uv run reterminal discover
export RETERMINAL_HOST=<device-ip>
uv run reterminal doctor
uv run reterminal status
uv run reterminal capabilities
uv run reterminal snapshot --png ./current.png
uv run reterminal probe
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews --push --live
uv run reterminal publish --feed examples/kitchen-display.json --watch --live
```

The CLI no longer falls back to a baked-in host IP. Set `RETERMINAL_HOST` or pass `--host` explicitly after discovery. Use `reterminal discover` and `reterminal doctor` when DHCP or network behavior is unclear; earlier leases are not stable identity.

## Package layout

```text
reterminal/
├── app/            # publish scenes -> previews/device slots
├── assets/fonts/   # bundled deterministic ePaper fonts + OFL license
├── cli/            # Typer commands
├── device/         # device SDK and capability model
├── family/         # PIL-free source parsers, agenda projections, calendar acquisition
├── payloads.py     # shared device/JSON payload types
├── protocols.py    # shared structural interfaces
├── providers/      # scene providers
├── render/         # monochrome renderer, layout primitives, bitmap generators
├── scheduler/      # slot assignment strategies
├── scenes/         # structured scene model
└── probe.py        # hardware verification tooling
```

## Scene feed example

The feed file at `examples/agent-feed.json` demonstrates the new format and is intentionally static demo content:

- `hero`
- `metrics`
- `bulletin`
- `poster`

These are logical scenes. The scheduler maps them into the 4 physical slots the firmware actually supports. Use a real feed or provider when you want the device to keep changing over time. Repeated publish loops skip unchanged slot uploads for better throughput; by default, pushes preserve the current visible slot, and `--show-slot <n>` explicitly selects a visible slot after pushing. Use interval publishing for demos/debugging only; production should use `--watch` so visible full-refreshes happen only when content actually changes. `poster` scenes can now render either a source image (`image_path`) or deterministic generated bitmap art via `meta.bitmap`.

Current providers include:

- `CalendarProvider` — large Today/Tomorrow columns, Week, Next, Prepare, and Weekend views from markdown or structured calendar JSON
- `MissionsProvider` — mission cards from a markdown file
- `EventsProvider` — upcoming events from a markdown file
- `ActivitiesProvider` — recent and queued activities from a markdown file
- `ComingUpProvider` — consolidated events and activities queue
- `CampsProvider` — current camp week plus a four-week lookahead
- `TripProvider` / `QuestProvider` — feature pages that read only an explicit `## Kitchen Display` block
- `PhotoProvider` — deterministic folder image selection and 1-bit dithering
- `FileSceneProvider` — generic scene-list JSON feed
- `PaperclipSceneProvider` — remote HTTP feed adapter
- `SystemSceneProvider` — device health scene

Providers are wired via a manifest JSON (`"providers": [{"type": "calendar", "path": "...", "slot": 0}, ...]`). Each type string maps to a factory in `providers/manifest.py::PROVIDER_REGISTRY`. Manifest-level `slot` pins are applied outside provider code so providers stay slot-agnostic. Trip and Quest entries can supply a nested `fallback` provider that inherits the slot when the primary source is missing, invalid, or expired.

Use `reterminal calendar-export` for complete-day Google Calendar acquisition. Use `reterminal doctor --publisher-url http://127.0.0.1:8765` to inspect delivery receipts while the device sleeps; unset `RETERMINAL_HOST` for a publisher-only check. See [calendar acquisition](../docs/calendar-source.md) and [delivery verification](../docs/delivery.md).

For the measured typography/layout approach behind these scenes, see `../docs/layout-system.md`.

## Legacy code

The old direct-script entrypoints (`python/reterminal.py`, `python/refresh.py`, and `python/pages/*`), `reterminal/pages/*`, and the old fixed-page `refresh` / `watch` CLI commands are gone from the active interface. Use provider manifests and `reterminal publish` for new work.

## Tests

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check reterminal tests
```
