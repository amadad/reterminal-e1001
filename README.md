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

### Install for agents

Install the CLI so it works from any folder:

```bash
cd python
uv tool install -e .
# or: pipx install .
```

Verify the installed command from outside the repo:

```bash
command -v reterminal
reterminal --help
python ../scripts/verify_agent_cli.py
```

Or with venv/pip:

```bash
cd python
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Discover and configure the device host

```bash
uv run reterminal discover
export RETERMINAL_HOST=<device-ip>
```

The CLI no longer falls back to a baked-in IP. Set `RETERMINAL_HOST` or pass `--host` explicitly after discovery. Do not assume an old DHCP lease; during recovery the device moved from earlier `.76/.77/.78` guesses to `.97`.

### 3. Probe the live device

```bash
uv run reterminal doctor
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

`python/examples/agent-feed.json` is static demo content. Use it for previews and smoke tests, not as a live ops feed.

### 5. Push the scheduled scenes to the device

Live device mutations now require explicit approval via `--live`:

```bash
uv run reterminal publish \
  --feed examples/agent-feed.json \
  --preview ./previews \
  --push \
  --live
```

To keep a real feed fresh and rotate the visible slot over time:

```bash
uv run reterminal publish \
  --feed path/to/live-feed.json \
  --push \
  --interval 60
```

Repeated publish runs now skip unchanged slot uploads within the same device uptime, so a steady feed loop does less unnecessary work. Use `--show-slot <n>` when you want to keep a specific slot visible instead of rotating across assigned slots.

## Agent-friendly CLI workflow

Use the CLI the same way a later coding agent will use it:

```bash
command -v reterminal
reterminal --help
reterminal config --output json
reterminal discover --output json
reterminal doctor --output json
reterminal push --text "hello" --preview ./preview.png --output json
reterminal publish --feed ./python/examples/agent-feed.json --preview ./previews --output json
```

Rules:
- use `--preview` or other read-only commands by default
- use `--output json` for machine-readable results
- use `--live` only after explicit user approval
- if a full artifact is large, write it to a file and return the path

## Feed-driven scene model

The new pipeline consumes structured scene JSON and maps it into the 4 physical slots.

Example file: `python/examples/agent-feed.json` (static demo content)

Supported scene kinds today:

- `hero`
- `metrics`
- `bulletin`
- `poster`

See `docs/layout-system.md` for the measured layout model behind those templates.

Current/ready provider adapters:

- local JSON feeds via `FileSceneProvider`
- ambient host scene via `SystemSceneProvider`
- remote Paperclip-compatible HTTP feed via `PaperclipSceneProvider`

This makes it easy to plug in:

- Paperclip agent feeds
- local status snapshots
- generated poster/image scenes
- deterministic bitmap posters via `meta.bitmap` (sparklines, bars, grids)
- weather/market/queue summaries

## CLI

```text
reterminal discover      Probe common names/IPs to find reachable devices
reterminal doctor        Check connectivity, slot truth, and publish readiness
reterminal status        Get raw device status
reterminal capabilities  Show firmware/host device contract
reterminal probe         Probe live device behavior
reterminal publish       Render/schedule/preview/push scene feeds
reterminal push          Push ad hoc text/image/QR/pattern
reterminal clear         Clear one slot or the full volatile cache
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
├── render/         # monochrome renderer, layout primitives, bitmap generators
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

The latest **verified live device** still reflects the older flashed firmware contract above.

The tracked firmware source has now been tightened to:

- remove hardcoded Wi-Fi credentials from source
- require local build-time config via `platformio.local.ini`
- disable OTA unless a password is configured
- reject invalid page indices instead of silently wrapping
- reject invalid `imageraw?page=N` targets instead of displaying them immediately
- expose `/capabilities` and `/clear` for a more truthful host contract
- use neutral slot names (`slot-0..slot-3`) instead of semantic app labels
- stop drawing firmware overlay chrome on top of uploaded bitmaps

Reflash and re-probe before treating those newer behaviors as live truth. The current flashed device has still shown the older `Page X/4` overlay and older endpoint set until reflashed.

## Legacy wrapper

`refresh.sh` now points at the active CLI, but it remains a legacy wrapper for the old fixed-page workflow and now requires `RETERMINAL_HOST` to be set explicitly.

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
