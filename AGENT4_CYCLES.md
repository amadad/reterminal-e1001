# Agent 4 — Circular Dependency Sweep

Scope: `python/reterminal/` (50 modules). Tooling: `grimp` for the import
graph plus `networkx.strongly_connected_components` / `simple_cycles` for
cycle detection. Firmware skipped per instructions.

## Critical assessment

### Baseline cycle report (before any edits)

```
Modules: 50
Non-trivial SCCs: 1
  SCC 0 (size 2):
    reterminal.cli.app
    reterminal.cli.commands
  edges:
    reterminal.cli.app      -> reterminal.cli.commands
    reterminal.cli.commands -> reterminal.cli.app
  simple cycle:
    reterminal.cli.app -> reterminal.cli.commands -> reterminal.cli.app
```

Only **one** real cycle in the entire package. Everything else is a clean
DAG.

### Cycle anatomy

`cli/app.py` constructs the Typer `app` object, then at the very bottom of
the file does:

```python
from reterminal.cli import commands  # noqa: F401, E402  -- import for side-effect registration
```

`cli/commands.py` decorates dozens of functions with `@app.command(...)`,
so it has to pull `app` back in:

```python
from reterminal.cli.app import app
```

This is the classic Typer/Click side-effect-registration idiom. It is a
**hard cycle at top-level import time** — neither side uses `TYPE_CHECKING`
or function-local imports. It happens to work because Python's import
machinery exposes the partially-initialised `cli.app` module (with `app`
already bound) when `commands.py` is loaded mid-way through `app.py`. It
is, however, exactly the kind of cycle that breaks if anyone reorders
imports in `app.py` so the `commands` import moves above the `app =
typer.Typer(...)` line. The `E402` noqa exists precisely to document and
suppress this fragility.

### Other suspected coupling sites — verified clean

Every site the prompt called out as historically risky is now one-way:

| Pair | Verdict |
| --- | --- |
| `providers.*` ↔ `family.*` | Clean. `providers/*` -> `family/*` only. The recent split is correct. |
| `app.live` ↔ `app.publisher` ↔ `cli.commands` | DAG: `cli.commands` -> `app.publisher`, `app.live` -> `app.publisher`. `cli.commands` lazily imports `app.live.run_live` inside the `publish --watch` handler (fine either way). |
| `client` ↔ `config` ↔ `exceptions` | `client` -> `config`, `client` -> `exceptions`. Neither leaf imports back. |
| `device.*` ↔ `protocols` | `protocols` -> `device.capabilities` -> `config`. `device.adapter` -> `protocols`? No — `device.adapter` imports `client`, `config`, `device.capabilities`, `encoding`, `exceptions`, `payloads`. No reverse edge from `device` into `protocols`. Clean. |

`TYPE_CHECKING` is used once (`scenes/models.py` for `PIL.Image`); it
guards an external dep, not a reterminal module, so there are no hidden
"soft" cycles being papered over.

## Recommendations

| Cycle | Confidence to break | Proposed minimal change |
| --- | --- | --- |
| `cli.app <-> cli.commands` | **H** | Extract the `app = typer.Typer(...)` instance into a tiny leaf module `cli/_typer_app.py`. Both `cli.app` and `cli.commands` import `app` from the leaf, eliminating the SCC. No behaviour change; preserves the `from reterminal.cli import commands` side-effect registration line in `cli/app.py`. |

No other cycles to break.

## Implemented

Single localised edit, three files touched (one new, two modified):

1. **New leaf module** `python/reterminal/cli/_typer_app.py` — holds the
   `app = typer.Typer(...)` instance and the top-level help/epilog strings.
   No reterminal imports, so it is a true leaf.
2. **`python/reterminal/cli/app.py`** — now `from reterminal.cli._typer_app
   import app`. Keeps the `@app.callback()` registration, the loguru
   configuration, and the trailing `from reterminal.cli import commands`
   side-effect import so `import reterminal.cli.app` still produces a fully
   wired CLI.
3. **`python/reterminal/cli/commands.py`** — single line change:
   `from reterminal.cli.app import app` -> `from reterminal.cli._typer_app
   import app`.

### Verification

```text
grimp + networkx after edit:
  Non-trivial SCCs: 0

pytest -q (python/, --extra dev):
  118 passed in 4.09s

ruff check reterminal/cli/:
  All checks passed
```

(Working-tree ruff has two pre-existing F-errors in `providers/photos.py`
that are independent of this change — confirmed by stashing and re-running
ruff against the clean baseline.)

CLI smoke tested: `reterminal --help` lists every registered subcommand;
`reterminal lint --help` resolves through the new import path.

## Risks and follow-ups

- **Low risk.** The new module is import-only and has no logic; the Typer
  instance is constructed identically. Subcommand registration order is
  unchanged because `cli.app` still imports `cli.commands` as the last line
  of its module body, exactly as before.
- The `noqa: F401, E402` on the side-effect import in `cli/app.py` is
  retained (still needed: it's a non-top-of-file import kept intentionally
  late so the loguru config block can run first, and it imports a module
  for its decorator side effects).
- No public API change. `reterminal.cli.app.app` still resolves (re-export
  via the `from reterminal.cli._typer_app import app` line at the top of
  `cli/app.py`), so external callers and `tests/test_commands.py` /
  `tests/test_brief.py` (which both `from reterminal.cli.app import app`)
  continue to work unchanged.
- Follow-up for a different agent: the pre-existing ruff failures in
  `reterminal/providers/photos.py` (`F401` unused `JSONValue`, `F821`
  undefined `Any`) are unrelated to cycles but should be fixed before this
  sweep merges.
