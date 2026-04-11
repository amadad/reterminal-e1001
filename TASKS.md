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
