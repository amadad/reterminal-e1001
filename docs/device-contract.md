# reTerminal device contract

Status: working draft, verification-first.

This file is the source of truth for the refactor. Do not treat the legacy README, AGENTS, or page tables as authoritative until the hardware verification steps in `docs/hardware-verification.md` have been completed on the real device.

## Why this exists

The repo has drifted in three places:

- **Firmware truth**: what the ESP32 firmware actually stores, renders, and navigates
- **Host truth**: what the Python package thinks the device supports
- **Docs truth**: what the README and agent docs claim

The refactor should converge those three into one contract.

## Latest verified live results (2026-03-13)

Automated probe was run successfully against the live device over Wi-Fi after USB serial revealed the current DHCP lease.

- **Observed IP during that probe:** `192.168.7.76`
- **Live SSID:** `HORUS`
- **Firmware-reported page total:** `4`
- **Verified contiguous storable/selectable slots:** `0..3`
- **Out-of-range upload behavior:** `POST /imageraw?page=4..7` returns `{"success": true, "displayed": true}` and displays immediately instead of storing
- **Out-of-range page set behavior:** `POST /page {"page": 4..7}` wraps modulo 4 and selects `0..3`
- **Large out-of-range page set behavior:** `POST /page {"page": 99}` returned page `3`
- **Invalid JSON behavior on `/page`:** malformed or empty JSON returned `200 OK` and left the current page unchanged
- **Invalid image size behavior:** short raw upload returned `400 Bad Request` with expected and received byte counts
- **Visual confirmation from user:** device visibly beeped/blinked and showed the checkerboard test pattern during the probe

Evidence artifact:

- `artifacts/probe-report.json`

Note: the tracked repo firmware has since been tightened to reject invalid page indices, reject invalid upload targets, and remove hardcoded Wi-Fi credentials from source. Those newer behaviors are **not live truth yet** until the device is reflashed and re-probed.

Operational note: DHCP lease is not a stable identity signal for this device. During a later recovery/publish session on `2026-04-01`, the same device was rediscovered at `192.168.7.97` and accepted live scene uploads. Treat observed IPs as session evidence, not as part of the device contract, and prefer `reterminal discover` / `reterminal doctor` before making network assumptions.

Later live operation also confirmed two more truths about the currently flashed device: power-cycling can return with `loaded: false` on the active slot, and the flashed firmware still showed the old `Page X/4` overlay plus no `/capabilities` or `/clear` endpoints until reflashed. Those are live observations of the older flashed build, not the newer tracked source.

## Current evidence from code inspection

These are facts supported by the current codebase, not yet by live hardware measurement.

| Area | Current evidence | Source | Confidence |
|---|---|---|---|
| Display format | 800x480, 1-bit monochrome, 48,000-byte raw payloads | `firmware/src/main.cpp`, `python/reterminal/config.py`, `python/reterminal/encoding.py` | High |
| Firmware page storage | Firmware allocates `NUM_PAGES = 4` page buffers | `firmware/src/main.cpp` | High |
| Host page model | Python package registers 7 pages: market, clock, github, status, portfolio, dashboard, weather | `python/reterminal/pages/__init__.py` | High |
| Control API | `/status`, `/capabilities`, `/buttons`, `/beep`, `/page`, `/imageraw`, `/clear` | `firmware/src/main.cpp` | High |
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

These must be measured on the real device before major refactor work is considered safe:

1. **Actual reliable page slot count**
   - Code says 4 slots today.
   - We need to verify how many slots are reliable on the real hardware.

2. **Invalid page behavior**
   - What happens for `POST /page {"page": 4}` or `{"page": -1}`?
   - Does the device wrap, reject, crash, or misrender?

3. **Stored page persistence**
   - Do page buffers survive reboot?
   - Do they survive OTA?

4. **Button parity with API**
   - Do physical buttons navigate exactly the same slot range as `/page`?

5. **Refresh characteristics**
   - Full refresh time
   - visual artifacts / ghosting
   - whether partial updates are worth supporting later

6. **OTA viability**
   - Is OTA required for ongoing use?
   - Does it work reliably on the current network?

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

### Required API behavior

| Endpoint | Requirement |
|---|---|
| `GET /status` | Returns stable health fields and basic capability fields |
| `GET /capabilities` | Returns firmware version, geometry, slot count, loaded slot map, and current slot info |
| `GET /buttons` | Returns current button state |
| `GET /page` | Returns current page and total slot count |
| `POST /page` | Rejects invalid input explicitly, no unsafe wraparound |
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

We are **not good yet**. The repo is only ready for structural refactor after:

1. automated probe results are captured
2. manual button/reboot/display checks are recorded
3. the verified slot count is written back into this document
4. the chosen architecture is updated in `docs/refactor-plan.md`

## Related docs

- `docs/hardware-verification.md`
- `docs/refactor-plan.md`
