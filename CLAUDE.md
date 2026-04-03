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

Based on live probing:

- device connects over Wi-Fi and exposes `/status`, `/buttons`, `/beep`, `/page`, `/imageraw`
- current live contract is `800x480`, `1-bit`, `48000` bytes per raw image
- current firmware exposes **4** physical slots
- out-of-range `POST /page` wraps modulo 4
- out-of-range `POST /imageraw?page=N` displays immediately instead of storing
- reboot currently clears usable cached pages enough that the host must republish

Tracked source has moved ahead of the flashed device: it adds `/capabilities`, `/clear`, neutral slot names, and removes the firmware `Page X/4` overlay, but those are not live truth until the device is reflashed.

See:

- `docs/device-contract.md`
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
│       ├── render/              # mono renderer + layout/bitmap primitives
│       ├── scheduler/
│       ├── scenes/
│       ├── pages/               # legacy fixed-page modules
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
uv run reterminal clear --all
uv run reterminal probe
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews --push
uv run reterminal publish --feed path/to/live-feed.json --push --interval 60
```

## Commands considered legacy

```bash
uv run reterminal refresh market
uv run reterminal watch clock -i 60
./refresh.sh market
python refresh.py
python reterminal.py
```

## Architectural rules

1. **Do not assume more than 4 physical slots** unless firmware changes and the probe is updated.
2. **Do not put Paperclip-specific logic in firmware or the device SDK.** Add it as a provider.
3. **Do not tie scene meaning to slot numbers.** Slots are physical; scenes are logical.
4. **Prefer provider/scene/scheduler/render boundaries** over page-specific scripts.
5. **Use `reterminal/device` for capability-aware slot operations** instead of hitting raw firmware semantics from new code.

## Design direction

The medium-term goal is a dynamic monochrome feed for agents and related systems:

- provider adapters for Paperclip and other sources
- stronger typography and layout templates
- monochrome poster/media pipeline
- scheduler strategies for pinned + rotating scenes

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
