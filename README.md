# reTerminal E1001

A host-rendered publishing pipeline for the Seeed reTerminal E1001 ePaper display.

The repo now treats the device as a **4-slot monochrome display appliance**:

- the **host** fetches data, designs scenes, renders images, and schedules what should be live
- the **firmware** stores bitmaps, shows slots, handles buttons, and exposes a small HTTP API

## Verified device contract

Live probe results from the current flashed firmware:

- **Resolution:** 800x480
- **Color depth:** 1-bit monochrome
- **Raw upload size:** 48,000 bytes
- **Physical page slots:** 4 (`0..3`)
- **Out-of-range `POST /page`:** wraps modulo 4
- **Out-of-range `POST /imageraw?page=N`:** displays immediately instead of storing

See:

- `docs/device-contract.md`
- `docs/hardware-verification.md`
- `artifacts/probe-report.json`

## What this repo does now

### Stable device layer

- probe the live device
- read status and capabilities
- upload raw monochrome images
- store/show slot `0..3`

### Host-side scene pipeline

- load scenes from providers
- schedule logical scenes into 4 physical slots
- render editorial monochrome layouts
- preview locally or push to the device

### Legacy page system

The older fixed page modules still exist for compatibility, but they are now **legacy**. The new direction is provider-driven scenes, not a hardcoded 7-page carousel.

## Quick start

### 1. Install the Python package

```bash
cd python
uv sync
```

Or with venv/pip:

```bash
cd python
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure the device host

```bash
export RETERMINAL_HOST=192.168.7.76
```

### 3. Probe the live device

```bash
uv run reterminal status
uv run reterminal capabilities
uv run reterminal probe
```

Destructive slot verification:

```bash
uv run reterminal probe --upload-pages --slots 8 --output ../artifacts/probe-report.json
```

### 4. Preview the new scene pipeline

```bash
uv run reterminal publish \
  --feed examples/agent-feed.json \
  --preview ./previews
```

### 5. Push the scheduled scenes to the device

```bash
uv run reterminal publish \
  --feed examples/agent-feed.json \
  --preview ./previews \
  --push
```

## Feed-driven scene model

The new pipeline consumes structured scene JSON and maps it into the 4 physical slots.

Example file: `python/examples/agent-feed.json`

Supported scene kinds today:

- `hero`
- `metrics`
- `bulletin`
- `poster`

Current/ready provider adapters:

- local JSON feeds via `FileSceneProvider`
- ambient host scene via `SystemSceneProvider`
- remote Paperclip-compatible HTTP feed via `PaperclipSceneProvider`

This makes it easy to plug in:

- Paperclip agent feeds
- local status snapshots
- generated poster/image scenes
- weather/market/queue summaries

## CLI

```text
reterminal status        Get raw device status
reterminal capabilities  Show host-side device contract
reterminal probe         Probe live device behavior
reterminal publish       Render/schedule/preview/push scene feeds
reterminal push          Push ad hoc text/image/QR/pattern
reterminal refresh       Legacy fixed-page refresh flow
reterminal watch         Legacy fixed-page watch flow
reterminal config        Show current configuration
reterminal buttons       Read button state
reterminal page          Get/set the current device slot
reterminal beep          Trigger the buzzer
```

## Architecture

```text
python/reterminal/
├── app/            # high-level publishing pipeline
├── device/         # truthful device SDK + capabilities
├── providers/      # scene sources (file feed, system, future Paperclip)
├── render/         # monochrome renderer + design tokens
├── scheduler/      # logical scenes -> physical slots
├── scenes/         # scene data model
├── cli/            # Typer CLI
├── pages/          # legacy fixed page modules
└── probe.py        # hardware verification tooling
```

### Design direction

The repo is moving toward:

- **provider adapters** for external systems like Paperclip
- **scene templates** for strong typography and layout
- **scheduler strategies** for deciding which 4 scenes are currently live
- **image/poster pipeline** for monochrome media generation

## Firmware notes

The current firmware is still a minimal HTTP server with buttons and OTA. The next firmware cleanup should:

- remove hardcoded Wi-Fi credentials
- add a `/capabilities` endpoint
- reject invalid page indices instead of silently wrapping
- explicitly expose slot names and loaded-state if useful

## Legacy wrapper

`refresh.sh` now points at the active CLI, but it remains a legacy wrapper for the old fixed-page workflow.

## Development

Run tests:

```bash
cd python
uv run --extra dev pytest -q
```

Lint changed modules:

```bash
cd python
uv run --extra dev ruff check reterminal tests
```

## Next integrations

Planned adapters and pipelines:

- Paperclip feed provider
- generated monochrome poster/image provider
- slot rotation policies
- stronger type hierarchy for scene templates

## License

MIT
