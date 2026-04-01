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
uv run reterminal discover
export RETERMINAL_HOST=<device-ip>
uv run reterminal doctor
uv run reterminal status
uv run reterminal capabilities
uv run reterminal probe
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews
uv run reterminal publish --feed examples/agent-feed.json --preview ./previews --push
uv run reterminal publish --feed path/to/live-feed.json --push --interval 60
```

The CLI no longer falls back to a baked-in host IP. Set `RETERMINAL_HOST` or pass `--host` explicitly after discovery. Use `reterminal discover` and `reterminal doctor` when DHCP or network behavior is unclear; earlier `.76/.77/.78` guesses are not stable identity.

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

The feed file at `examples/agent-feed.json` demonstrates the new format and is intentionally static demo content:

- `hero`
- `metrics`
- `bulletin`
- `poster`

These are logical scenes. The scheduler maps them into the 4 physical slots the firmware actually supports. Use a real feed or provider when you want the device to keep changing over time. Repeated publish loops skip unchanged slot uploads within the same device uptime for better throughput, and `--show-slot <n>` lets you pin the visible slot after each push.

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

They remain for compatibility while the repo transitions to the provider/scene/scheduler model. Legacy fixed pages are now guarded against pushing to slots beyond the live device capacity.

## Tests

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check reterminal tests
```
