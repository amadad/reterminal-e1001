# AGENTS.md

Instructions for AI agents working in this repository.

## Source of truth

Before making architecture claims, use these files:

- `docs/device-profile.md`
- `docs/hardware-verification.md`
- `docs/refactor-plan.md`
- `artifacts/probe-report.json`

The current flashed firmware is verified as a **4-slot** device, not a 7-slot carousel.

## Mental model

Treat this repo as a small publishing system for a monochrome ePaper target.

- **Firmware**: bitmap storage, display, buttons, HTTP API
- **Host SDK**: capability discovery, safe slot operations
- **Scene pipeline**: providers -> scenes -> scheduler -> renderer -> device

Do not center new work around the legacy fixed-page system unless explicitly asked.

## Verified constraints

- Resolution: `800x480`
- Format: `1-bit`
- Raw image bytes: `48000`
- Physical slots: `0..3`
- Live firmware now exposes `/capabilities`, `/clear`, and `/snapshot`
- Live slot names are neutral: `slot-0..slot-3`
- `snapshot_readback` is live and can return the exact stored raw bitmap for a loaded slot
- loaded slots persist to LittleFS across normal reboot/power cycle; host republish is still the recovery path after reflash, empty storage, or filesystem failure
- on `kunst`, curl-based transport remains more reliable than Python `requests` for live device mutations

The checked-in `artifacts/probe-report.json` describes the older pre-reflash firmware. Do not assume its old invalid-input wraparound behavior is still the current live contract until the reflashed device is probed again.

## Active Python modules

```text
python/reterminal/
├── app/            # publish scenes to previews/device slots
├── cli/            # active CLI
├── device/         # device SDK + capabilities
├── payloads.py     # shared device/JSON payload types
├── protocols.py    # shared structural interfaces
├── providers/      # scene adapters
├── render/         # monochrome layouts, bitmap generators, art handling, viz primitives (see docs/visualizations.md)
├── scheduler/      # logical scenes -> 4 slots
├── scenes/         # scene schema
├── pages/          # legacy fixed page flow
└── probe.py        # verification tooling
```

## Core commands

```bash
cd ~/projects/reterminal-e1001/python

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

## Decommissioned legacy commands

The old fixed-page `refresh` / `watch` CLI commands are no longer part of the active interface. Use `reterminal publish` with provider manifests instead. `refresh.sh` is retained only as a decommissioning pointer.

## Design direction

Prefer these extension points:

- **providers** for Paperclip, local feeds, generated media, etc.
- **renderers/templates** for strong typography and layout
- **scheduler strategies** for slot rotation
- **device capabilities** for hardware-aware behavior

Avoid baking external integrations directly into firmware or into slot-specific host code.

## Safety rule

Preview first. Live device mutations should require explicit `--live` approval and should refuse `--non-interactive` mutation attempts. `publish --push` stages changed slots without changing the visible page unless `--show-slot` is explicit.

## When adding features

1. keep the device SDK small and truthful
2. put external system logic behind providers/adapters
3. keep scene data structured, not pre-rendered
4. make renderers responsible for visual composition
5. never assume more than 4 physical slots unless firmware changes and is re-probed

## Verification

For code changes, run targeted tests from `python/`:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check reterminal tests
```

For live-device work, probe first:

```bash
uv run reterminal discover
uv run reterminal doctor
uv run reterminal capabilities
uv run reterminal clear --all
uv run reterminal probe
```

DHCP leases are not stable identity. Do not hardcode earlier `.76/.77/.78` guesses; a later recovery session rediscovered the device at `.97`.
