# reTerminal E1001

A host-rendered publishing pipeline for the Seeed reTerminal E1001 ePaper display.

The repo now treats the device as a **4-slot monochrome display appliance**:

- the **host** fetches data, designs scenes, renders images, and schedules what should be live
- the **firmware** stores bitmaps, shows slots, handles buttons, pulls changed content on timer wake, and exposes a short-lived diagnostic API

## Verified device profile

Prior live probing and board verification confirm the hardware envelope:

- **Resolution:** 800x480
- **Color depth:** 1-bit monochrome
- **Raw upload size:** 48,000 bytes
- **Physical page slots:** 4 (`0..3`)

The checked-in `artifacts/probe-report.json` is sanitized historical evidence
for the 4-slot hardware and the pre-pull firmware. It predates the tracked
deep-sleep refactor; regenerate it after the next physical flash before using
it as evidence for the current diagnostic contract.

See:

- `docs/device-profile.md`
- `docs/hardware-verification.md`
- `artifacts/probe-report.json`

## What this repo does now

### Stable device layer

- probe the live device
- read diagnostic status and derive the fixed display capabilities
- upload raw monochrome images
- store/show slot `0..3`

### Host-side scene pipeline

- load scenes from providers
- schedule logical scenes into 4 physical slots
- render editorial monochrome layouts
- preview locally or push to the device

### Removed legacy page system

The older fixed page modules have been removed. The active direction is provider-driven scenes, not a hardcoded carousel.

## Quick start

For connection and troubleshooting notes, including USB-vs-HTTP and Python/uv path rules, see `docs/access.md`.

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

The CLI no longer falls back to a baked-in IP. Set `RETERMINAL_HOST` or pass `--host` explicitly after discovery. Do not assume an old DHCP lease remains valid.

### 3. Probe the live device

```bash
uv run reterminal doctor
uv run reterminal status
uv run reterminal capabilities
uv run reterminal snapshot --png ./current.png
uv run reterminal probe
```

Destructive slot verification:

```bash
uv run reterminal probe --upload-pages --live --slots 8 --expected-pages 4 --output ../artifacts/probe-report.json
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

To keep the kitchen display fresh in production, use the provider manifest with
the FSEvents watcher. In the current deep-sleep architecture this serves content
on port 8765; the device pulls changed slots on wake.

```bash
uv run reterminal publish \
  --feed examples/kitchen-display.json \
  --watch \
  --live
```

For host health, verify the publisher on the MacBook LAN IP, not only
localhost:

```bash
curl -fsS --max-time 3 http://<macbook-lan-ip>:8765/content-hash
```

If localhost works but the LAN IP hangs, fix macOS Application Firewall for the
Python runtime used by `uv`; the physical device uses the LAN path.

## Agent-friendly CLI workflow

Use the CLI the same way a later coding agent will use it:

```bash
command -v reterminal
reterminal --help
reterminal config --output json
reterminal discover --output json
reterminal doctor --output json
reterminal snapshot --png ./current.png --output json
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
reterminal snapshot      Read back a stored slot bitmap
reterminal probe         Probe live device behavior
reterminal publish       Render/schedule/preview scene feeds or serve pull content
reterminal push          Push ad hoc text/image/QR/pattern during diagnostics
reterminal config        Show current configuration
reterminal page          Get/set the current device slot during diagnostics
```

## Architecture

```text
python/reterminal/
├── app/            # high-level publishing pipeline
├── cli/            # Typer CLI
├── device/         # truthful device SDK + capabilities
├── payloads.py     # shared device/JSON payload types
├── protocols.py    # shared structural interfaces
├── providers/      # scene sources (file feed, system, future Paperclip)
├── render/         # monochrome renderer, layout primitives, bitmap generators
├── scheduler/      # logical scenes -> physical slots
├── scenes/         # scene data model
└── probe.py        # hardware verification tooling
```

### Design direction

The repo is moving toward:

- **provider adapters** for external systems like Paperclip
- **scene templates** for strong typography and layout
- **scheduler strategies** for deciding which 4 scenes are currently live
- **image/poster pipeline** for monochrome media generation

## Firmware notes

Tracked firmware is the deep-sleep/pull implementation in
`firmware/src/main.cpp`; the last checked-in physical probe predates it.

Current source truth includes:

- build-time Wi-Fi / OTA config via `platformio.local.ini`
- host pull endpoints `/content-hash` and `/content/slot-N`
- a 10-minute diagnostic API: `/status`, `/eventlog`, `/snapshot`, `/imageraw`, `/page`, `/sleep`
- neutral slot names (`slot-0..slot-3`) and no firmware overlay chrome
- LittleFS-backed slot persistence with write success checked before advancing content hashes
- host-derived capabilities and curl fallback for macOS routing failures

## Legacy wrapper

The old fixed-page `refresh` / `watch` CLI commands and `reterminal/pages/*` modules are not part of the active interface. `refresh.sh` is kept only as a decommissioning pointer to the provider-driven publish flow.

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

The original host-side code is MIT. Firmware distribution needs an explicit
license review because it links the GPLv3 GxEPD2 library; do not treat the root
MIT file as resolving the combined firmware binary's obligations.
