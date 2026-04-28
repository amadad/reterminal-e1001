# TASKS

Source: review against OpenAI's agent-friendly CLI guide:
https://developers.openai.com/codex/use-cases/agent-friendly-clis

## Goal
Make `reterminal` a safe, composable, installable CLI that agents can use for discovery, inspection, preview, and explicitly approved live writes.

## P0

- [x] **RETERM-1: Add machine-readable output to all key commands**
  - Add consistent JSON output to commands that still print ad-hoc text, especially:
    - `push`
    - `publish`
    - `page`
    - `buttons`
    - `clear`
    - `config`
    - `beep`
  - Prefer one consistent interface: `--json` everywhere or `--output json` everywhere
  - **Acceptance:** all key agent-facing commands return stable structured output and structured errors

- [x] **RETERM-2: Add explicit approval boundaries for live device writes**
  - Make live mutation require explicit opt-in, e.g. `--live` and/or confirmation
  - Add `--non-interactive` refusal for live writes
  - Keep preview-only paths easy and safe
  - **Acceptance:** `push`/`publish --push` cannot mutate the device accidentally in automation

- [x] **RETERM-3: Add install-from-any-folder workflow**
  - Document install via `uv tool install -e ./python` and/or `pipx install ./python`
  - Add smoke test from outside the repo
  - **Acceptance:** `command -v reterminal` works outside the repo and `reterminal --help` succeeds

## P1

- [x] **RETERM-4: Standardize file output paths**
  - Make previews, probe reports, and publish artifacts land in predictable locations
  - Return those paths clearly in both text and JSON
  - **Acceptance:** agents can reliably find generated files without scraping terminal output

- [x] **RETERM-5: Add companion skill for recurring use**
  - Create a skill that teaches future agents to:
    - run discovery first
    - run doctor second
    - preview before push
    - ask approval before live device mutation
  - **Acceptance:** agents can invoke a named skill instead of rereading repo docs

- [x] **RETERM-6: Add README agent-friendly CLI section**
  - Document:
    - install
    - verify from another folder
    - safe discovery command
    - exact read command
    - preview-to-file workflow
    - live-write approval rule
  - **Acceptance:** README mirrors the guide's recommended usage pattern

## P2

- [x] **RETERM-7: Improve discovery → exact-read workflow**
  - Make the path from `discover` to `status` / `capabilities` / `page` more explicit
  - Optionally add a helper to select or persist a discovered host
  - **Acceptance:** agents can move from finding a device to inspecting one target with minimal ambiguity

## Notes from current review
- Discovery, doctor, preview, and file outputs are already strong
- Biggest gaps are write safety and JSON consistency on mutating commands
- Current docs still assume repo-local `uv run` usage

---

# Review tasks — firmware, efficiency, and live use

Source: repo review on 2026-04-27 after live kitchen-display pipeline and Wi-Fi/TWDT firmware fixes.

## P0 — correctness and operational safety

- [x] **RETERM-R1: Reconcile current firmware truth across docs and probe artifacts**
  - Update `README.md`, `python/README.md`, `firmware/README.md`, `docs/device-profile.md`, and `AGENTS.md`/`CLAUDE.md` so they agree on:
    - 4 physical slots (`0..3`)
    - `/capabilities`, `/snapshot`, `/clear` live support
    - current invalid-input behavior after reflash
    - LittleFS slot persistence vs historical volatile-cache notes
  - Clearly mark `artifacts/probe-report.json` as historical unless replaced.
  - **Acceptance:** no doc claims old wraparound/display-immediate semantics as current live truth unless a fresh probe proves it.

- [x] **RETERM-R2: Make `reterminal probe` compatible with current clean-reject firmware**
  - Accept `current_page_name` as well as legacy `page_name` in expected status/formatting.
  - During destructive slot probing, treat `400 Page out of range` from `/imageraw?page=N` or `/page` as an observed clean rejection instead of aborting the whole probe.
  - Record rejected-invalid-slot results in JSON with explicit notes.
  - **Acceptance:** probing slots `0..7` against a 4-slot reject-cleanly firmware completes and reports slots `4..7` as rejected, not crashed.

- [x] **RETERM-R3: Remove hardcoded production device IP from launchd path**
  - Replace `scripts/sh.reterminal.publish.plist`'s fixed `RETERMINAL_HOST` with one of:
    - mDNS host (`reterminal.local`) once firmware advertises it reliably
    - a wrapper that runs discovery and exports the selected host
    - a documented router DHCP reservation
  - **Acceptance:** production refresh survives DHCP lease changes without editing the plist.

- [x] **RETERM-R4: Make the live publish cache retry-safe**
  - In `python/reterminal/app/live.py`, do not mark a slot digest as current until the upload succeeds.
  - Add a test where `push_pil()` fails once and the next tick retries the same changed bitmap.
  - **Acceptance:** a transient upload failure cannot cause the watcher to skip the slot forever.

## P1 — efficiency and product fit

- [x] **RETERM-R5: Avoid unnecessary visible refreshes and flash writes for unchanged slot uploads**
  - Add firmware-side no-op detection before `memcpy` / `saveSlotToFlash()` / `showPage()` in `/imageraw` handling.
  - Return a machine-readable skipped result, e.g. `{ "success": true, "page": N, "skipped": true }`.
  - Keep host-side hash skipping, but make firmware robust against dumb clients.
  - **Acceptance:** uploading byte-identical raw data to the currently visible slot does not full-refresh the panel or rewrite LittleFS.

- [x] **RETERM-R6: Seed live-loop state from `/snapshot` on startup**
  - On `publish --watch --push` startup, read loaded slot snapshots and seed per-slot digests before rendering/pushing.
  - Fall back to current behavior if `/snapshot` is unavailable or a slot is empty.
  - **Acceptance:** restarting the launchd watcher does not repush unchanged slots already present on the device.

- [x] **RETERM-R7: Stop promoting interval-based visible rotation for production**
  - Update docs to prefer `publish --watch --live` for kitchen display operation.
  - Reframe `--interval` as demo/debug only, or require `--show-slot` guidance to avoid minute-by-minute visible flips.
  - **Acceptance:** README examples no longer recommend `--interval 60` as the live kitchen-display path.

- [x] **RETERM-R8: Decide the legacy fixed-page fate and remove contradictions**
  - Either restore guarded `refresh` / `watch` CLI commands or delete the stale docs/wrapper claims.
  - If retaining legacy pages, ensure default slots above 3 are blocked or remapped before live push.
  - **Acceptance:** `README.md`, `python/README.md`, `refresh.sh`, and `reterminal --help` agree.

- [x] **RETERM-R9: Make ad-hoc no-page pushes explicit**
  - Today `reterminal push` without `--page` draws transiently but does not store a navigable slot.
  - Require a slot by default, or add an explicit `--transient` flag for direct display-only pushes.
  - **Acceptance:** users cannot accidentally create display state that `/snapshot`, reboot persistence, and buttons do not understand.

## P2 — firmware hardening and maintainability

- [x] **RETERM-R10: Improve firmware health/capability telemetry**
  - Add fields such as reset reason, Wi-Fi status, reconnect attempt count, last reconnect time, LittleFS total/used, free PSRAM, last display/upload error.
  - Surface them through `/status` or `/capabilities` and update host payload types.
  - **Acceptance:** `reterminal capabilities --output json` can explain likely Wi-Fi/storage/display health without serial logs.

- [x] **RETERM-R11: Make OTA and mDNS more reliable**
  - Add mDNS setup for the configured hostname and HTTP service.
  - Ensure OTA starts after a later Wi-Fi reconnect, not only when Wi-Fi was connected during `setup()`.
  - Document the macOS firewall workaround or whitelist path.
  - **Acceptance:** `reterminal.local` is discoverable and OTA availability recovers after Wi-Fi reconnect.

- [x] **RETERM-R12: Avoid destructive LittleFS auto-format on ordinary mount failure**
  - Revisit `LittleFS.begin(true)` and prefer no auto-format or an explicit recovery mode.
  - **Acceptance:** a transient filesystem mount problem cannot silently erase all stored slots.

- [x] **RETERM-R13: Tighten local firmware secret handling**
  - Fix `firmware/platformio.local.example.ini` so it does not use the recursive `${env:reterminal.build_flags}` pattern.
  - Consider moving local Wi-Fi/OTA secrets outside the repo tree or into environment-generated flags.
  - **Acceptance:** setup docs do not tell users to copy a known-recursive example, and common `pio project config` use does not casually expose real secrets in repo logs.

- [x] **RETERM-R14: Align PlatformIO flash/partition config with verified hardware**
  - Hardware verification says 32MB flash, but PlatformIO reports the selected board as 8MB.
  - Set explicit flash size / partition layout if the board and bootloader support it.
  - **Acceptance:** firmware build output and `docs/device-profile.md` agree on usable flash capacity and LittleFS budget.

## P3 — renderer/content workflow polish

- [x] **RETERM-R15: Unify preview scripts with production providers**
  - Make `examples/preview_family.py` and `examples/preview_missions.py` import provider parse/render functions instead of duplicating them.
  - Keep `preview_viz.py` as the visualization showcase.
  - **Acceptance:** preview PNGs and live provider output cannot drift due to duplicated layout code.

- [x] **RETERM-R16: Render explicit empty/stale states for markdown-backed slots**
  - Calendar should show an intentional empty agenda when Today/Tomorrow are empty, not leave stale content by returning no scene.
  - Add subtle source mtime / stale indicators where useful.
  - **Acceptance:** missing source, empty source, and stale source have distinct visible behaviors.

- [x] **RETERM-R17: Cache font loading in kitchen providers**
  - Use shared cached font helpers rather than repeated direct `ImageFont.truetype()` calls.
  - **Acceptance:** repeated live renders avoid redundant font loads and providers share the same Helvetica fallback behavior.

- [x] **RETERM-R18: Sync Python dependency metadata**
  - Remove stale `python/requirements.txt` or generate it from `pyproject.toml`.
  - **Acceptance:** there is one authoritative Python dependency list.

- [x] **RETERM-R19: Add CI for host and firmware checks**
  - Add a minimal workflow for:
    - `cd python && uv run --extra dev pytest -q`
    - `cd python && uv run --extra dev ruff check reterminal tests`
    - `cd firmware && platformio run`
  - **Acceptance:** pull requests catch CLI/doc drift and firmware build breaks before flashing.

## Completion evidence

- `cd python && uv run --extra dev pytest -q` → `72 passed`
- `cd python && uv run --extra dev ruff check reterminal tests` → passed
- `cd firmware && platformio run` → `reterminal` and `ota` succeeded; build now reports `32MB Flash`
- `platformio run` also succeeds with `platformio.local.ini` temporarily absent, matching CI/no-secret setup
- `plutil -lint scripts/sh.reterminal.publish.plist` → OK; `bash -n scripts/reterminal-publish-watch.sh refresh.sh` → OK
- `uv run python examples/preview_missions.py` and `uv run python examples/preview_family.py` wrote preview PNGs under `/tmp/reterminal-review/`
- Live device flash/probe was not run in this pass; firmware changes are source/build verified only.
