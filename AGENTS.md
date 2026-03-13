# AGENTS.md

Instructions for AI agents working in this repository.

## Source of truth

Before making architecture claims, use these files:

- `docs/device-contract.md`
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
- `POST /page` wraps modulo 4 for out-of-range values
- `POST /imageraw?page=N` displays immediately instead of storing for out-of-range slots

## Active Python modules

```text
python/reterminal/
├── app/            # publish scenes to previews/device slots
├── cli/            # active CLI
├── device/         # device SDK + capabilities
├── providers/      # scene adapters
├── render/         # monochrome layouts and art handling
├── scheduler/      # logical scenes -> 4 slots
├── scenes/         # scene schema
├── pages/          # legacy fixed page flow
└── probe.py        # verification tooling
```

## Core commands

```bash
cd ~/projects/reterminal-e1001/python

uv run reterminal status
uv run reterminal capabilities
uv run reterminal probe
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews --push
```

## Legacy commands

These still exist but are not the preferred architecture:

```bash
uv run reterminal refresh market
uv run reterminal watch clock -i 60
./refresh.sh market
```

## Design direction

Prefer these extension points:

- **providers** for Paperclip, local feeds, generated media, etc.
- **renderers/templates** for strong typography and layout
- **scheduler strategies** for slot rotation
- **device capabilities** for hardware-aware behavior

Avoid baking external integrations directly into firmware or into slot-specific host code.

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
uv run reterminal capabilities
uv run reterminal probe
```
