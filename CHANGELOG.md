# Changelog

## Unreleased

### Added
- Explicit `--live` / `--non-interactive` safety gates for live device mutations.
- JSON output for more agent-facing commands, including `push`, `publish`, `page`, `clear`, `config`, and `beep`.
- Installed-command verification script at `scripts/verify_agent_cli.py`.
- Reusable reTerminal skill for repeat agent workflows.
- Launchd wrapper that discovers the DHCP-assigned device before starting the kitchen-display watcher.
- CI workflow for Python tests, ruff, and PlatformIO firmware builds.
- Firmware health telemetry for Wi-Fi reconnects, mDNS/OTA readiness, reset reason, PSRAM, and LittleFS usage.

### Changed
- Updated docs to prefer preview-first workflows and explicit approval before pushing to the device.
- Updated docs and probe handling for the current clean-reject firmware contract.
- Kitchen-display providers now render explicit missing/empty states and share cached font helpers.
- Ad-hoc live pushes now require a stored `--page` unless `--transient` is explicit.
- `publish --push` preserves the current visible slot unless `--show-slot` is explicit, avoiding unnecessary full-panel refreshes.
- `reterminal probe` now defaults to the verified 4-slot expectation.
