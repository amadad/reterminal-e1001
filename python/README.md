# Python package

The Python package is the active control plane for the reTerminal E1001.

It now has two layers:

- a **truthful device SDK** for the current 4-slot firmware contract
- a **scene publishing pipeline** for provider-driven monochrome layouts

## Verified contract

The live device currently behaves as:

- 800x480 monochrome
- 48,000-byte raw upload payloads
- 4 physical slots
- current tracked firmware rejects invalid `page` requests with `400 Page out of range`
- current tracked firmware rejects invalid `imageraw?page=N` uploads with `400 Page out of range`
- current flashed firmware persists loaded slots in LittleFS across normal power cycles

Use `reterminal probe` and `reterminal capabilities` before assuming anything else. On newer firmware builds, `reterminal capabilities` reads the firmware-reported contract from `/capabilities`, `reterminal snapshot` can read back the exact stored slot bitmap, and `reterminal clear --all` can blank the stored slot cache for ghosting/recovery workflows.

## Install

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
uv run reterminal clear --all
uv run reterminal probe
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews --push --live
uv run reterminal publish --feed examples/kitchen-display.json --push --watch --live
```

The CLI no longer falls back to a baked-in host IP. Set `RETERMINAL_HOST` or pass `--host` explicitly after discovery. Use `reterminal discover` and `reterminal doctor` when DHCP or network behavior is unclear; earlier `.76/.77/.78` guesses are not stable identity.

## Package layout

```text
reterminal/
├── app/            # publish scenes -> previews/device slots
├── cli/            # Typer commands
├── device/         # device SDK and capability model
├── payloads.py     # shared device/JSON payload types
├── protocols.py    # shared structural interfaces
├── providers/      # scene providers
├── render/         # monochrome renderer, layout primitives, bitmap generators
├── scheduler/      # slot assignment strategies
├── scenes/         # structured scene model
├── pages/          # legacy fixed page system
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

- `FileSceneProvider`
- `SystemSceneProvider`
- `PaperclipSceneProvider` (remote HTTP feed adapter)

For the measured typography/layout approach behind these scenes, see `../docs/layout-system.md`.

## Legacy code

The following are still present but are no longer the architectural center:

- `reterminal/pages/*`

The old direct-script entrypoints (`python/reterminal.py`, `python/refresh.py`, and `python/pages/*`) plus the old fixed-page `refresh` / `watch` CLI commands are not part of the active interface. Use provider manifests and `reterminal publish` for new work.

## Tests

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check reterminal tests
```
