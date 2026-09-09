# reTerminal device profile

Status: tracked-source profile; current pull firmware awaits physical re-probe.

Use the **Current evidence from code inspection** section for the tracked
contract. Dated live sections document older flashed builds and must not be
projected onto the current source without a new hardware run.

## Why this exists

The repo has drifted in three places:

- **Firmware truth**: what the ESP32 firmware actually stores, renders, and navigates
- **Host truth**: what the Python package thinks the device supports
- **Docs truth**: what the README and agent docs claim

The refactor should converge those three into one canonical device profile.

## Last verified pre-pull firmware results (2026-05-04)

These results belong to the always-on firmware flashed before the 2026-05-12
deep-sleep/pull refactor. They verify the physical 4-slot device but not the
tracked diagnostic API. Network and serial identifiers are intentionally
public-safe and should be rediscovered per session.

- **USB flash:** succeeded via `/dev/cu.usbserial-*` using PlatformIO `env:reterminal`
- **Firmware provenance:** `/capabilities` reports `firmware_version: local-dev`, build time `May 4 2026`, and a `build_sha` matching the current dirty checkout
- **Firmware match check:** `reterminal doctor --host <device-ip> --feed <manifest> --output json` reports `firmware_match: match`
- **Wi-Fi/HTTP:** `/status`, `/capabilities`, `/page`, `/snapshot`, and `/imageraw` reachable over HTTP; CLI falls back to curl on hosts where Python `requests` reports `No route to host`
- **LittleFS persistence:** live boot log shows `LittleFS ready`, `Loaded slot 0..3 from flash`, and `Restored 4 slots from flash`; `/capabilities` reports LittleFS total/used bytes and all four slots loaded after reboot
- **Launchd watcher:** local watcher runs `publish --watch --live` from the ignored local manifest, discovers the DHCP host, seeds 4 slot digests from `/snapshot`, and preserves the visible slot
- **Destructive slot probe:** `artifacts/probe-report.json` confirms slots `0..3` store/select normally on that pre-pull build and rejects invalid slots `4..7`
- **Stability status:** bounded Wi-Fi self-restart firmware is flashed and reports `wifi_down_ms`, `self_restart_count`, `last_self_restart_reason`, and `loop_watchdog_armed`; final closure gate is still a 48–72h soak with reachable `/status`, acceptable reset reasons, and clean watcher logs

## Earlier verified live results (2026-04-16)

The device was physically attached to a macOS host over USB-C, interrogated through the ESP bootloader, reflashed from `firmware/`, and then re-verified over Wi-Fi. Network and serial identifiers below are intentionally public-safe and should be rediscovered per session.

- **Observed IP after reflash:** DHCP-assigned private address (session-specific; sanitized)
- **Live SSID:** configured 2.4GHz network (sanitized)
- **USB serial path:** `/dev/cu.usbserial-*` or `/dev/cu.usbmodem*` (session-specific suffix)
- **USB bridge identity:** `VID:PID 1A86:7523` (`CH340`-class USB serial bridge)
- **Chip identity:** `ESP32-S3 (QFN56)` revision `v0.2`
- **Clock:** `40MHz`
- **PSRAM:** embedded `8MB`
- **Flash:** `32MB`, quad, `3.3V`
- **Boot log after corrected local config:** allocated 4 page buffers, initialized the display, joined Wi-Fi, started the HTTP server, and enabled OTA
- **Firmware-reported geometry:** `800x480`, `1-bit`, `48000` bytes
- **Verified physical slot count:** `4` slots (`0..3`)
- **Live capability endpoints:** `/status`, `/capabilities`, `/buttons`, `/beep`, `/page`, `/snapshot`, `/imageraw`, `/clear`
- **Live slot naming:** neutral `slot-0..slot-3`
- **Snapshot readback:** `snapshot_readback: true`; `GET /snapshot?page=0` returns `404` while a slot is empty and returns an exact `48000`-byte raw bitmap after upload
- **Byte-for-byte readback proof:** the SHA-256 of the uploaded slot-0 raw bitmap matched the returned `/snapshot?page=0` payload exactly
- **Persistence semantics:** current firmware saves loaded slots to LittleFS and restores them on normal reboot/power cycle when the filesystem mounts successfully; reboot/reflash can still require host republish if storage is empty or unavailable
- **Current republished state during this session:** all four slots loaded and slot 0 visible
- **Measured visible page refresh time:** `POST /page {"page": 0}` clustered around `~5.5s` on repeated runs (`2.73s`, `5.52s`, `5.53s`; average `4.59s`)
- **Measured visible-slot upload time:** uploading a full bitmap to the currently visible slot took `~5.54s` on repeated runs
- **Measured hidden-slot upload time:** uploading a full bitmap to a non-visible loaded slot took `~0.19s` on repeated runs and did not change the visible page
- **Interaction model:** one visible full-screen bitmap at a time; left button = previous slot, middle button = next slot, right button = redraw current slot

Evidence artifacts:

- serial bootloader interrogation via `esptool.py read_mac` / `flash_id`
- serial boot logs on the macOS host
- local `/snapshot` readback captures (not committed; keep live snapshots under ignored `artifacts/snapshots/` or `artifacts/local/`)

Operational notes:

- DHCP lease is not a stable identity signal for this device. Treat observed IPs as session evidence, not as part of the device contract, and prefer discovery/doctor before making network assumptions.
- On some macOS hosts, plain `curl` has been more reliable than Python `requests` for live device transport.
- `/capabilities`, `/clear`, `/buttons`, and `/beep` in this dated section are historical endpoints, not part of tracked pull firmware.
- The practical performance model is: hidden-slot staging is cheap, visible-slot changes are slow. Design for preloading plus infrequent visible flips, not animation or second-by-second interaction.
- Current invalid-input semantics are re-verified by the sanitized destructive probe report. Repeat the probe only after firmware changes that touch slot validation/storage.

## Historical live results before reflash (2026-03-13 / 2026-04-01)

These results describe the older flashed firmware that was replaced on `2026-04-16`. Keep them as historical context when interpreting older notes; the checked-in probe report now reflects the current reflashed firmware.

- **Observed IP during the older probe:** DHCP-assigned private address (sanitized)
- **Later recovered IP on the same hardware:** different DHCP-assigned private address (sanitized)
- **Live SSID on the older build:** configured 2.4GHz network (sanitized)
- **Firmware-reported page total:** `4`
- **Verified contiguous storable/selectable slots:** `0..3`
- **Out-of-range upload behavior:** `POST /imageraw?page=4..7` returned `{"success": true, "displayed": true}` and displayed immediately instead of storing
- **Out-of-range page set behavior:** `POST /page {"page": 4..7}` wrapped modulo 4 and selected `0..3`
- **Large out-of-range page set behavior:** `POST /page {"page": 99}` returned page `3`
- **Invalid JSON behavior on `/page`:** malformed or empty JSON returned `200 OK` and left the current page unchanged
- **Invalid image size behavior:** short raw upload returned `400 Bad Request` with expected and received byte counts
- **Visible older-firmware quirks:** `Page X/4` overlay chrome, no `/capabilities`, no `/clear`, and cache state that could come back effectively unloaded after power cycle

The sanitized `artifacts/probe-report.json` replaced the oldest wraparound
evidence, but it is itself now historical because it predates pull firmware.

## Measured operating constraints (2026-04-16)

These are the practical design constraints supported by live measurement on the reflashed device.

- **Visible screen updates are slow:** budget roughly `5–6s` for a full visible refresh.
- **Hidden-slot staging is fast:** uploading to a non-visible slot is roughly `0.2s`.
- **Only one slot is visible at a time:** the 4 slots are a cache/navigation model, not 4 simultaneous regions.
- **Firmware stores full-screen bitmaps, not semantic UI widgets:** all composition happens on the host.
- **No touch / cursor / scroll / text input path exists in the current firmware:** interaction is limited to previous, next, and redraw.
- **Monochrome output only:** any gray appearance must come from host-side dithering.
- **Current cache is persistent but recoverable:** LittleFS-backed slots survive normal reboot on the current build, but host republish remains the recovery path after reflash, storage failure, or empty slots.
- **Current product fit:** ambient dashboards, posters, briefings, and low-frequency status surfaces fit well; animation and high-frequency UI do not.

## Current evidence from code inspection

These are facts supported by the current codebase, not yet by live hardware measurement.

| Area | Current evidence | Source | Confidence |
|---|---|---|---|
| Display format | 800x480, 1-bit monochrome, 48,000-byte raw payloads | `firmware/src/main.cpp`, `python/reterminal/config.py`, `python/reterminal/encoding.py` | High |
| Firmware page storage | Firmware allocates `NUM_PAGES = 4` page buffers | `firmware/src/main.cpp` | High |
| Host page model | Provider manifests select logical scenes and pin the four kitchen slots; the legacy fixed-page registry has been removed | `python/examples/kitchen-display.json`, `python/reterminal/providers/manifest.py` | High |
| Control API | Diagnostic-mode only (`GET /status`, `GET /eventlog`, `GET /snapshot`, `GET/POST /page`, `POST /imageraw`, `POST /sleep`). In normal operation the firmware is an HTTP client; it has no listening port. | `firmware/src/main.cpp` | High |
| Upload semantics | Tracked firmware now rejects invalid or out-of-range `page` uploads with `400` instead of falling back to display-immediately mode | `firmware/src/main.cpp` | High |
| Page set semantics | Tracked firmware now rejects invalid page numbers explicitly instead of wrapping them | `firmware/src/main.cpp` | High |
| Slot naming | Tracked firmware source now uses neutral slot names (`slot-0..slot-3`) instead of legacy semantic page labels | `firmware/src/main.cpp` | High |
| Display chrome | Tracked firmware source no longer overlays `Page X/4` on top of host-rendered bitmaps | `firmware/src/main.cpp` | High |
| Security posture | WiFi creds are no longer hardcoded in source; OTA is disabled unless a password is configured; HTTP endpoints are still unauthenticated | `firmware/src/main.cpp`, `firmware/platformio.local.example.ini` | Medium |
| Firmware health | The firmware is a deep-sleep + HTTP-pull client; normal cycles produce no live API. Diagnostic-mode `GET /status` exposes uptime, boot count, battery_mv, RSSI, free heap, slot state, build SHA; `GET /eventlog` returns a persistent ring buffer of boot, wake_timer, wake_button, diagnostic, and wifi_fail events with battery + RSSI snapshots, useful for post-mortems. | `firmware/src/main.cpp` | High |
| Shell wrapper | `refresh.sh` now points at the active provider-driven publish flow; the launchd wrapper prefers the ignored local manifest when present | `refresh.sh`, `scripts/reterminal-publish-watch.sh` | High |

## Provisional architecture assumption

Until hardware verification says otherwise, the refactor should assume this model:

1. **Host renders and serves pages**
   - Python fetches external data and renders 1-bit bitmaps
   - the LAN publisher serves per-slot hashes and raw bitmaps

2. **Firmware pulls, caches, and displays**
   - timer wake fetches changed slots and persists them
   - button wake navigates cached slots
   - a physical long press pulls fresh content, then enables the diagnostic API and OTA window
   - navigation preserves the existing next-poll deadline
   - pulls report stored hashes and returned refresh-call evidence to the host

3. **Firmware does not own external integrations**
   - no Schwab/GitHub/weather logic on the ESP32
   - no page-specific network logic in firmware

## Remaining live verification questions

These are the remaining checks before calling the physical deployment fully closed:

1. **Stored page persistence beyond USB flash/reboot**
   - Normal reboot persistence is verified on the current build: all four slots restored from LittleFS after reset.
   - OTA persistence should still be rechecked after the next OTA-capable flash.

2. **Button parity with API**
   - Do physical buttons navigate the same four slots as diagnostic `/page` after flashing tracked pull firmware?

3. **Refresh characteristics**
   - Earlier live timing measured visible refreshes at about `5–6s`
   - visual artifacts / ghosting still need manual optical verification
   - tracked firmware intentionally uses full refresh only

4. **OTA viability in repeated use**
   - Is OTA reliable enough to keep in the default workflow over time?
   - Does it preserve expected cache behavior?

5. **Receipt and polling behavior**
   - Activate the hash-query-capable host before the new firmware.
   - Verify three changed editions through unattended timer receipts, including
     navigation across a polling deadline. See [delivery.md](delivery.md).

## Tracked contract to verify

The host owns the fixed geometry (`800x480`, 48,000 bytes, four slots).
Diagnostic `/status` reports firmware/build provenance, current and loaded slots,
battery, RSSI, heap, boot count, and event-log count. There is deliberately no
second `/capabilities` representation.

### Required API behavior

Normal pull contract:

| Endpoint | Requirement |
|---|---|
| host `GET /content-hash` | Returns four per-slot SHA-256 hashes, or null for unassigned slots |
| host `GET /content/slot-N` | Returns exactly 48,000 raw bytes for a loaded cache entry |
| host `GET /content/slot-N?hash=<digest>` | Returns the requested content or 409 if the edition changed |
| host `GET /health` | Separately reports sources, rendering, HTTP requests, and device receipts |
| host `POST /receipt` | Validates and persists device-reported stored hashes and refresh-call evidence |

Diagnostic-mode device contract:

| Endpoint | Requirement |
|---|---|
| `GET /status` | Returns provenance, health, slot count, current slot, and loaded map |
| `GET /page` | Returns current page and total slot count |
| `POST /page` | Rejects invalid input explicitly, no unsafe wraparound |
| `GET /snapshot` | Returns the exact stored raw bitmap or a clear error |
| `POST /imageraw?page=N` | Stores valid slot `N` only after a full LittleFS write |
| `GET /eventlog` | Returns the persistent wake/diagnostic/Wi-Fi/pull/receipt outcome ring |
| `POST /sleep` | Returns the device to deep sleep immediately |

### Required host behavior

- Derive slot state from diagnostic `/status` before manual slot operations
- Never assume 7 slots unless the firmware proves it
- Treat external integrations as optional providers, not core runtime requirements
- Prefer one Python path: `python/reterminal/`
- Do not infer device storage from served bytes or optical success from
  `refresh_returned` / `displayed_hash`; those describe a returned driver call.

## Decision rules

- Treat four slots as fixed until both firmware and a fresh probe prove otherwise.
- Do not claim persistence until the post-flash power-cycle check passes.
- Keep OTA outside the default workflow unless it remains password-protected and reliable.

## Verification gate

The tracked architecture is structurally coherent but physical closure still requires:

1. flash the tracked pull firmware and regenerate `artifacts/probe-report.json`
2. record button, display, snapshot, and LittleFS persistence checks
3. observe several timer wakes with successful pulls and no repeated `wifi_fail` events

## Related docs

- `docs/hardware-verification.md`
- `docs/refactor-plan.md`
