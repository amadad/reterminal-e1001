# reTerminal device profile

Status: working draft, verification-first.

This file is the source of truth for the refactor. Do not treat the legacy README, AGENTS, or page tables as authoritative until the hardware verification steps in `docs/hardware-verification.md` have been completed on the real device.

## Why this exists

The repo has drifted in three places:

- **Firmware truth**: what the ESP32 firmware actually stores, renders, and navigates
- **Host truth**: what the Python package thinks the device supports
- **Docs truth**: what the README and agent docs claim

The refactor should converge those three into one canonical device profile.

## Latest verified live results (2026-04-16)

The device was physically attached to `kunst` over USB-C, interrogated through the ESP bootloader, reflashed from `firmware/`, and then re-verified over Wi-Fi.

- **Observed IP after reflash:** `192.168.7.32`
- **Live SSID:** `HORUS`
- **USB serial path on `kunst`:** `/dev/cu.usbserial-1410`
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
- **Cache semantics after reboot/reflash:** device booted with `current_page_loaded: false` and `loaded_pages: [false,false,false,false]` until the host republished
- **Current republished state during this session:** all four slots loaded and slot 0 visible
- **Measured visible page refresh time:** `POST /page {"page": 0}` clustered around `~5.5s` on repeated runs (`2.73s`, `5.52s`, `5.53s`; average `4.59s`)
- **Measured visible-slot upload time:** uploading a full bitmap to the currently visible slot took `~5.54s` on repeated runs
- **Measured hidden-slot upload time:** uploading a full bitmap to a non-visible loaded slot took `~0.19s` on repeated runs and did not change the visible page
- **Interaction model:** one visible full-screen bitmap at a time; left button = previous slot, middle button = next slot, right button = redraw current slot

Evidence artifacts:

- serial bootloader interrogation via `esptool.py read_mac` / `flash_id`
- serial boot logs on `kunst`
- `artifacts/snapshots/slot-0-live.raw`
- `artifacts/snapshots/slot-0-live.png`

Operational notes:

- DHCP lease is not a stable identity signal for this device. Earlier sessions saw `.76` and `.97`; this reflashed session came back at `.32`. Treat observed IPs as session evidence, not as part of the device contract, and prefer discovery/doctor before making network assumptions.
- On `kunst`, plain `curl` remains more reliable than Python `requests` for live device transport, so the `oc-min` curl bridge is still the preferred mutation path on that machine.
- As of this session, `/capabilities`, `/clear`, `/snapshot`, neutral slot names, and no firmware overlay chrome are now **live truth**, not just tracked-source intent.
- The practical performance model is: hidden-slot staging is cheap, visible-slot changes are slow. Design for preloading plus infrequent visible flips, not animation or second-by-second interaction.
- A fresh destructive probe is still required before treating the reflashed firmware's invalid-input semantics as fully re-verified live behavior.

## Historical live results before reflash (2026-03-13 / 2026-04-01)

These results describe the older flashed firmware that was replaced on `2026-04-16`. Keep them as historical evidence when interpreting older notes and `artifacts/probe-report.json`.

- **Observed IP during the older probe:** `192.168.7.76`
- **Later recovered IP on the same hardware:** `192.168.7.97`
- **Live SSID on the older build:** `HORUS`
- **Firmware-reported page total:** `4`
- **Verified contiguous storable/selectable slots:** `0..3`
- **Out-of-range upload behavior:** `POST /imageraw?page=4..7` returned `{"success": true, "displayed": true}` and displayed immediately instead of storing
- **Out-of-range page set behavior:** `POST /page {"page": 4..7}` wrapped modulo 4 and selected `0..3`
- **Large out-of-range page set behavior:** `POST /page {"page": 99}` returned page `3`
- **Invalid JSON behavior on `/page`:** malformed or empty JSON returned `200 OK` and left the current page unchanged
- **Invalid image size behavior:** short raw upload returned `400 Bad Request` with expected and received byte counts
- **Visible older-firmware quirks:** `Page X/4` overlay chrome, no `/capabilities`, no `/clear`, and cache state that could come back effectively unloaded after power cycle

Historical evidence artifact:

- `artifacts/probe-report.json`

## Measured operating constraints (2026-04-16)

These are the practical design constraints supported by live measurement on the reflashed device.

- **Visible screen updates are slow:** budget roughly `5–6s` for a full visible refresh.
- **Hidden-slot staging is fast:** uploading to a non-visible slot is roughly `0.2s`.
- **Only one slot is visible at a time:** the 4 slots are a cache/navigation model, not 4 simultaneous regions.
- **Firmware stores full-screen bitmaps, not semantic UI widgets:** all composition happens on the host.
- **No touch / cursor / scroll / text input path exists in the current firmware:** interaction is limited to previous, next, and redraw.
- **Monochrome output only:** any gray appearance must come from host-side dithering.
- **Current cache should be treated as volatile:** reboot/reflash can require host republish before any slot is usable again.
- **Current product fit:** ambient dashboards, posters, briefings, and low-frequency status surfaces fit well; animation and high-frequency UI do not.

## Current evidence from code inspection

These are facts supported by the current codebase, not yet by live hardware measurement.

| Area | Current evidence | Source | Confidence |
|---|---|---|---|
| Display format | 800x480, 1-bit monochrome, 48,000-byte raw payloads | `firmware/src/main.cpp`, `python/reterminal/config.py`, `python/reterminal/encoding.py` | High |
| Firmware page storage | Firmware allocates `NUM_PAGES = 4` page buffers | `firmware/src/main.cpp` | High |
| Host page model | Python package registers 7 pages: market, clock, github, status, portfolio, dashboard, weather | `python/reterminal/pages/__init__.py` | High |
| Control API | `/status`, `/capabilities`, `/buttons`, `/beep`, `/page`, `/snapshot`, `/imageraw`, `/clear` | `firmware/src/main.cpp` | High |
| Upload semantics | Tracked firmware now rejects invalid or out-of-range `page` uploads with `400` instead of falling back to display-immediately mode | `firmware/src/main.cpp` | High |
| Page set semantics | Tracked firmware now rejects invalid page numbers explicitly instead of wrapping them | `firmware/src/main.cpp` | High |
| Slot naming | Tracked firmware source now uses neutral slot names (`slot-0..slot-3`) instead of legacy semantic page labels | `firmware/src/main.cpp` | High |
| Display chrome | Tracked firmware source no longer overlays `Page X/4` on top of host-rendered bitmaps | `firmware/src/main.cpp` | High |
| Security posture | WiFi creds are no longer hardcoded in source; OTA is disabled unless a password is configured; HTTP endpoints are still unauthenticated | `firmware/src/main.cpp`, `firmware/platformio.local.example.ini` | Medium |
| Shell wrapper | `refresh.sh` now requires `RETERMINAL_HOST` explicitly and points at the active CLI; legacy fixed pages are fenced to the live slot count in the CLI | `refresh.sh`, `python/reterminal/cli/commands.py` | High |

## Provisional architecture assumption

Until hardware verification says otherwise, the refactor should assume this model:

1. **Host renders pages**
   - Python fetches external data
   - Python renders 1-bit bitmaps
   - Python uploads finished images to the device

2. **Firmware acts as display/cache/navigation**
   - store bitmap in slot `N`
   - display slot `N`
   - next/prev page navigation
   - buttons
   - status endpoints
   - OTA if explicitly kept and secured

3. **Firmware does not own external integrations**
   - no Schwab/GitHub/weather logic on the ESP32
   - no page-specific network logic in firmware

## Open questions that require live hardware verification

These still need fresh measurement on the reflashed device before major architecture claims are considered safe:

1. **Current-firmware invalid page behavior**
   - What happens now for `POST /page {"page": 4}` or `{"page": -1}`?
   - Does the reflashed firmware reject cleanly exactly as source suggests?

2. **Current-firmware invalid upload behavior**
   - What happens now for `POST /imageraw?page=4` on the reflashed build?
   - Does it reject cleanly or still show any fallback behavior?

3. **Stored page persistence**
   - Do page buffers survive a normal reboot?
   - Do they survive OTA?

4. **Button parity with API**
   - Do physical buttons navigate exactly the same slot range and naming as `/page` on the reflashed build?

5. **Refresh characteristics**
   - Preliminary live timing is now known: visible refreshes are about `5–6s`, hidden-slot staging about `0.2s`
   - visual artifacts / ghosting still need manual optical verification
   - whether partial updates are worth supporting later remains open

6. **OTA viability in repeated use**
   - Is OTA reliable enough to keep in the default workflow over time?
   - Does it preserve expected cache behavior?

## Contract we want after verification

Once verified, the firmware contract should be explicit and machine-readable.

### Required firmware-reported capabilities

The device should eventually expose enough information for the host to adapt without guessing:

- firmware version
- display width
- display height
- `image_bytes`
- page slot count
- current page
- loaded page map, if cheap to expose
- optional build info / git SHA
- whether slot snapshot readback is supported

### Required API behavior

| Endpoint | Requirement |
|---|---|
| `GET /status` | Returns stable health fields and basic capability fields |
| `GET /capabilities` | Returns firmware version, geometry, slot count, loaded slot map, and current slot info |
| `GET /buttons` | Returns current button state |
| `GET /page` | Returns current page and total slot count |
| `POST /page` | Rejects invalid input explicitly, no unsafe wraparound |
| `GET /snapshot` | Returns the exact stored raw bitmap for a loaded slot or a clear error if none is stored |
| `POST /imageraw?page=N` | Either stores slot `N` or returns a clear error |
| `POST /clear` | Clears one slot or the full volatile cache without inventing host-side content |

### Required host behavior

- Read device-reported slot count before assuming page capacity
- Never assume 7 slots unless the firmware proves it
- Treat external integrations as optional providers, not core runtime requirements
- Prefer one Python path: `python/reterminal/`

## Decision rules for the refactor

- If the verified slot count is **4**, the host may still expose more logical pages, but only 4 may be cached on-device at once.
- If the verified slot count is **7 or more**, then a true 7-page carousel is allowed.
- If stored pages do **not** survive reboot, reboot persistence must not be part of the contract.
- If OTA is flaky or insecure, remove it from the default workflow until secured.

## Verification gate

We are closer, but **not done yet**. The repo is only ready for structural closure after:

1. a fresh probe report is captured against the reflashed firmware
2. manual button/reboot/display checks are recorded on that reflashed firmware
3. the remaining invalid-input / persistence questions above are answered with evidence
4. the chosen architecture is updated in `docs/refactor-plan.md`

## Related docs

- `docs/hardware-verification.md`
- `docs/refactor-plan.md`
