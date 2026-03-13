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
- invalid `page` requests wrap modulo 4
- invalid `imageraw?page=N` uploads display immediately instead of storing

Use `reterminal probe` and `reterminal capabilities` before assuming anything else.

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
uv run reterminal status
uv run reterminal capabilities
uv run reterminal probe
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews --push
```

## Package layout

```text
reterminal/
├── app/            # publish scenes -> previews/device slots
├── cli/            # Typer commands
├── device/         # device SDK and capability model
├── providers/      # scene providers
├── render/         # monochrome renderer + design tokens
├── scheduler/      # slot assignment strategies
├── scenes/         # structured scene model
├── pages/          # legacy fixed page system
└── probe.py        # hardware verification tooling
```

## Scene feed example

The feed file at `examples/agent-feed.json` demonstrates the new format:

- `hero`
- `metrics`
- `bulletin`
- `poster`

These are logical scenes. The scheduler maps them into the 4 physical slots the firmware actually supports.

Current providers include:

- `FileSceneProvider`
- `SystemSceneProvider`
- `PaperclipSceneProvider` (remote HTTP feed adapter)

## Legacy code

The following are still present but are no longer the architectural center:

- `reterminal/pages/*`
- `reterminal refresh`
- `reterminal watch`
- `python/reterminal.py`
- `python/refresh.py`
- `python/pages/*`

They remain for compatibility while the repo transitions to the provider/scene/scheduler model.

## Tests

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check reterminal tests
```
