# Solutions log

Newest first. Keep entries short, dated, and evidence-oriented.

## 2026-05-12 — Stripped to idiomatic deep-sleep + pull architecture

- **Symptoms / why this entry exists:** Every "freeze" we'd been fixing since 2026-04-27 was a symptom of running the wrong architecture (always-on HTTP server with `WiFi.setSleep(false)`) on the wrong power source (the unit has a Li-Po battery and Seeed claims ~3-month life). The 2026-05-11 event log shipped the day before captured 229 POWERON-class resets with RTC RAM wiped each time, zero `wifi_lost` events, zero `restart_*` events — i.e. brownout cycling during battery depletion, not zombie LWIP or anything firmware-level. Each prior "fix" (ARP keepalive, HTTP-idleness, 12h periodic restart, loop watchdog, manual reconnect) was chasing a symptom of the wrong base architecture.
- **Reference architecture:** Seeed's own production port for this device — `https://github.com/Seeed-Projects/Seeed_TRMNL_Eink_Project`. Its `main.cpp` is 6 lines. Business logic is modular. **HTTP client only, no HTTP server in firmware.** Boot flow: init → WiFi → exchange MAC for API key → fetch BMP → display → deep sleep. ~78 days of battery at 15-min refresh.
- **Fix:** rewrote `firmware/src/main.cpp` from 1402 → 710 lines, single-file, matching the idiomatic shape. The firmware now deep-sleeps and is a pull-mode HTTP client. Wake (timer every `RETERMINAL_WAKE_INTERVAL_S`, default 1800s, or EXT1 button) → connect WiFi → GET `/content-hash` from publisher → fetch only the slots whose hash changed → save to LittleFS → refresh ePaper → `esp_deep_sleep_start`. Long-press right button (3s) enters diagnostic mode (HTTP server + mDNS + OTA up for 10 min then back to sleep).
- **Host fix:** rewrote `python/reterminal/app/live.py` from 504 → 274 lines. Deleted `_OnlineTracker`, `_sync_cache_with_device`, `_try_recover_device`, `_seed_cache_from_device`, `_push_cache_to_device` — all push-mode machinery. The publisher now runs an HTTP server on port 8765 with `GET /content-hash` (per-slot SHA-256s) and `GET /content/slot-N` (raw 48000-byte bitmap). FSEvents on `~/madad/family/*.md` re-render to the in-memory cache; the device pulls from us when it wakes.
- **Wrapper fix:** `scripts/reterminal-publish-watch.sh` dropped its blocking-discovery loop and the `--push` flag. The publisher no longer needs to know the device's IP; the device knows the publisher's IP.
- **Deleted entirely from firmware:** `maintainWifi`, `restartForHealth`, the `SELF_RESTART_*` enum, HTTP-idleness restart, WiFi self-restart timer, periodic 12h restart, loop watchdog at top level (only inside diagnostic mode now), ARP keepalive (already gone), 5-min heartbeat to flash, `markClientActivity` + `lastClientMs` + `httpRequestCount` plumbing, three `showXxxScreen` variants collapsed into one `showCenteredScreen`, 10 HTTP handlers collapsed to 6 (gated behind diagnostic mode). About ~700 lines of pure deletion in firmware, ~230 lines in host.
- **Battery math under the new shape:** ~9s awake per 1800s cycle = 0.5% duty cycle. At 100 mA active and 10 µA sleep: ~0.5 mA average. **750 mAh / 0.5 mA ≈ 60 days** at 30-min wake. Matches Seeed's 78-day claim at their 15-min interval.
- **Side feature landed in the same window:** `python/reterminal/providers/_poster_fetcher.py` fetches Wikipedia article main-images for [movie]/[series] queue items (no API key). Persistent cache at `~/.cache/reterminal/posters/`. The activities renderer already had inset-poster support but was pointed at `/tmp/...` which got wiped on reboot.
- **Evidence:** Build successful at 27.8% flash, 29.8% RAM (similar to before; deletions roughly balanced by added http-client code). Flashed `843d087-dirty` 2026-05-12 12:31:57. Cold boot verified via serial: setup completes in 10.4s, then `Deep sleep: 1800s or button. uptime=10432ms`. Publisher restarted via launchd; `curl http://127.0.0.1:8765/content-hash` returns real per-slot SHA-256s within ~10s of bootstrap (no retry storms; was 60-90s of timeouts before the strip). 113/113 pytest, ruff clean.
- **Lesson written down explicitly so the next person doesn't repeat it:** every "freeze" / "zombie WiFi" / "stack wedge" theory we accreted between 2026-04-27 and 2026-05-11 was downstream of the architecture mismatch. The right move when the user said "Seeed claims months of battery, we're getting 36-48h" was to compare to Seeed's own firmware reference, not to keep adding retry timers and watchdogs to an always-on shape. Cost of not doing that earlier: ~10 commits of patches on top of patches.

## 2026-05-11 — Overnight freeze returned despite ARP keepalive; added HTTP-idleness detector, persistent event log, host log hygiene

- **Symptoms:** Kitchen display froze overnight again. On wake-up the screen still showed yesterday's persisted slot bitmaps (LittleFS-cached), but the device was unreachable on Wi-Fi for hours. After manual power-cycle, `/capabilities` reported `reset_reason: poweron`, `self_restart_count: 0`, `last_self_restart_reason: none` — neither `wifi_stale` nor the 12h `periodic` ceiling fired before the user unplugged. Publisher had been retry-spinning at `192.168.7.94` and grew `publish.log` to 52 MB.
- **Why prior fixes did not catch it:** every existing restart path depends on a signal the zombie state can mask. `wifi_stale` requires `WiFi.status() != WL_CONNECTED`; the zombie LWIP state keeps reporting `WL_CONNECTED`. `periodic` only fires at 12h uptime and the freeze entered well before that. The loop watchdog stays fed because the loop itself keeps iterating. ARP keepalive can return success while the underlying stack no longer transmits — none of these prove an actual client reached the device. The May-7 ARP-cache-expiry theory was plausible but never confirmed with packet evidence, and ran for three nights without preventing the next freeze.
- **Fix — HTTP-idleness detector:** new `HTTP_IDLE_RESTART_MS` (default 30 min, override via `RETERMINAL_HTTP_IDLE_RESTART_MS`). `markClientActivity()` is called from every HTTP handler; the loop restarts (`SELF_RESTART_HTTP_IDLE`) when WiFi reports connected and >30 min have passed since the last accepted client AND we've seen at least one client this boot. Pure `millis()` comparison — no blocking calls, no `WiFiClient.connect()` (the 2026-05-06 footgun). Surfaced via new `/capabilities` fields `http_idle_restart_ms`, `last_client_ms`, `http_idle_ms`, `http_request_count`.
- **Fix — Persistent event ring buffer:** 16-entry ring at `/eventlog.bin` (LittleFS) with magic header. Appended on boot, wifi_lost, wifi_restored, and every `restartForHealth()`. New `GET /eventlog` returns the buffer as JSON. Lets the next post-mortem reconstruct what fired (or didn't fire) across freeze + recovery without serial logs. `event_log_total` and `event_log_capacity` exposed in `/capabilities`.
- **Fix — Host publisher log hygiene:** `client.py` demoted per-attempt `Connection failed` and tenacity `before_sleep` log lines to DEBUG. `live.py` gained `_OnlineTracker` that emits one transition log per online↔offline change instead of ~20 lines per failed tick. After restart, the log went from 52 MB / ~533k lines to a handful of lines per minute.
- **Side mystery resolved:** USB-serial output appeared dead because we were reading the wrong path. The reTerminal exposes two USB-CDC bridges: `/dev/cu.usbserial-*` (CH340, `VID 1A86:7523`) carries `Serial1` on GPIO 43/44 and is the correct path for both flashing and serial monitoring. `/dev/cu.usbmodem*` (CH343, `VID 1A86:55D3`) is a different bridge with no firmware-side output. esptool auto-reset only works through the CH340 path; the CH343 path failed with `No serial data received` because RTS/DTR don't reach EN on it.
- **Evidence:** Built `27.8% flash, 29.8% RAM` (unchanged size). Flashed `fe176d1584e1-dirty` at `May 11 2026 11:41`. Post-flash `/capabilities` returns `http_idle_restart_ms: 1800000`, `http_request_count` advancing under publisher polling, `event_log_total: 1` with the boot entry. `/eventlog` returns `magic_ok: true` and the boot event. `uv run --extra dev pytest -q` passes (`118 passed`), ruff clean. Publisher restarted via `launchctl kickstart -k`; log reseed shows two lines instead of thousands. Overnight soak pending — the next freeze post-mortem reads `/capabilities` + `/eventlog` *before* power-cycling to confirm whether the new detector fired.
- **Open question if the new detector also fails to recover:** the failure is below the loop's awareness (loop watchdog should catch but doesn't, periodic restart never fires, HTTP-idleness never fires). That would imply a deeper IDF/PHY-level wedge and the right answer would be a hardware power cycle (smart plug) rather than another firmware patch.

## 2026-05-07 — Idiomatic WiFi fixes: ARP keepalive + auto-reconnect + 12h last-resort restart

- **Root cause (revised):** Two compounding mechanisms. (1) Home routers expire ARP entries after 5-30 min of silence. A quiet display device's IP becomes unroutable even though the 802.11 association is intact — this is what "zombie WiFi" looks like from the host. (2) The previous manual reconnect loop (`WiFi.setAutoReconnect(false)` + `WiFi.disconnect() + WiFi.begin()` on a 30s interval) fights the ESP32 driver's internal state machine and can itself introduce the LWIP corruption it was trying to fix.
- **Fix 1 — Gratuitous ARP every 4 minutes:** `sendGratuitousArp()` iterates `netif_list` and calls `etharp_gratuitous()` on each ETHARP-capable interface. This keeps the router's ARP entry for the device alive indefinitely. The standard embedded mechanism; no new state, no reconnect logic.
- **Fix 2 — `WiFi.setAutoReconnect(true)`:** The ESP32 driver's designed reconnect mechanism. Removes all manual `WiFi.disconnect() + WiFi.begin()` calls from `maintainWifi()`. The function now only monitors state transitions, manages mDNS/OTA lifecycle, and triggers `SELF_RESTART_WIFI_STALE` if the driver fails to recover within 10 min. Dead variables removed: `lastWifiRetryMs`, `WIFI_GRACE_MS`, `WIFI_RETRY_INTERVAL_MS`.
- **Fix 3 — Periodic restart extended to 12h:** ARP keepalive + driver-managed reconnect are the primary defenses. The unconditional restart is now a genuine last resort (LWIP stack itself corrupts). 12h gives enough headroom to catch a multi-day failure without firing every night.
- **`sdkconfig.defaults` considered and rejected:** Would reduce `CONFIG_LWIP_TCP_MSL` (TIME_WAIT) and set `CONFIG_LWIP_MAX_SOCKETS`. Doesn't apply to the Arduino ESP32 framework — LWIP config is compiled into the pre-built framework, not overridable via `sdkconfig.defaults` in PlatformIO.
- **Evidence:** Build successful (27.8% flash, 29.8% RAM). `etharp_gratuitous()` links from Arduino ESP32's bundled LWIP. `/capabilities` reports `arp_keepalive_ms: 240000`, `last_arp_ms`. Overnight soak pending.

## 2026-05-07 — Periodic restart reduced from 6h to 2h; proactive WiFi cycle rejected as overengineering

- **Symptoms:** overnight freezing persisted despite 6h periodic restart.
- **Root cause:** the maximum zombie window equals `PERIODIC_RESTART_MS`. A 6h ceiling means a zombie that enters 1 minute after a restart leaves the device unreachable for ~6h. An 8h overnight sleep can span two such windows.
- **Fix:** reduce `PERIODIC_RESTART_MS` from 21600000 (6h) to 7200000 (2h). Max zombie window is now ≤2h; an 8h overnight sleep sees at most 3 transparent restarts (~10-20s each, display stays on LittleFS-persisted content). Override via `RETERMINAL_PERIODIC_RESTART_MS` in `platformio.local.ini`.
- **Considered and rejected:** a proactive WiFi cycle (disconnect+reconnect every 2h even when link appears healthy). Same zombie window, but adds ~30 lines of new state and interaction with the existing reconnect logic. The "lighter than a restart" argument doesn't hold — the display shows persisted content immediately on boot; a 2s ePaper flash at 2am is not a real cost. Simpler wins.
- **Evidence:** build successful (27.8% flash, 29.8% RAM); overnight soak pending.

## 2026-05-06 — Periodic restart ceiling reduced from 23h to 6h

- **Symptoms:** device still froze overnight (8-12h) despite the 23h unconditional restart added on May 5. The 23h restart is correct in principle, but the freeze window (up to 22h before the ceiling fires) is too long for overnight use.
- **Root cause:** zombie WiFi can enter at any point during uptime, not just at hour 23. The 23h ceiling only guarantees recovery within 23h; it does nothing for a zombie state that enters at hour 8.
- **Failed attempt:** added a TCP health check (`probe.connect(gateway:80)`) to detect zombie state proactively. This caused a restart loop because `WiFiClient::connect()` ignores `setTimeout()` for the *connection* phase — it uses TCP retransmission timers (~20-75s) when the router silently drops SYNs. This exceeded the 60s loop-task watchdog, causing a watchdog panic and restart every ~6 minutes. Removing `WiFi.setSleep(false)` would NOT fix this; the issue is the blocking connect call, not sleep mode.
- **Fix:** reduce `RETERMINAL_PERIODIC_RESTART_MS` default from 82800000 (23h) to 21600000 (6h). Maximum zombie window is now 6h; the display recovers transparently via LittleFS on each restart. No new code paths; firmware is identical to the May 5 build except this threshold. Override via `RETERMINAL_PERIODIC_RESTART_MS` in `platformio.local.ini` if a longer window is needed.
- **Evidence:** build successful; firmware flashed 2026-05-06; `/capabilities` will report `periodic_restart_ms: 21600000`. Overnight soak pending.
- **Lesson:** on ESP32 Arduino, `WiFiClient.setTimeout()` only affects read operations, not `connect()`. TCP connect timeout is controlled by LWIP retransmission config and cannot be shortened via the Arduino WiFiClient API. Any TCP-connect-based health check will block for 20-75s on silent SYN drops — longer than any reasonable loop watchdog.

## 2026-05-06 — draw.fontmode = "1" applied across all render sites

- **Symptoms:** text rendered on ePaper appeared with faint antialiased grey pixels around edges, visible as dot-matrix texture after 1-bit thresholding.
- **Root cause:** Pillow's default `ImageDraw` uses antialiased font rendering (`fontmode = "L"`). For 1-bit ePaper targets, this produces sub-pixel greyscale that gets thresholded to noisy dots.
- **Fix:** set `draw.fontmode = "1"` after every `ImageDraw.Draw()` call in the render pipeline (providers/activities, calendar, events, missions; render/bitmap, kitchen, mono; cli/commands; encoding.py). This forces 1-bit (binary) font rasterization consistently.
- **Evidence:** `uv run --extra dev pytest -q` passes; ruff passes.

## 2026-05-05 — Unconditional 23h restart added to defeat zombie Wi-Fi

- **Symptoms:** device froze overnight requiring a power cycle, despite the May 4 Wi-Fi self-restart fix. `reset_reason: poweron` after each freeze confirmed the self-restart never triggered.
- **Root cause:** all previous restart paths were conditional on `wifiLinkUp()` returning false or `loop()` blocking. The "zombie Wi-Fi" state (ESP32 LWIP stack corrupted, `WiFi.status() == WL_CONNECTED` but TCP dead) bypasses both: the link appears up so no restart fires, and the loop keeps running so the watchdog stays fed. The device is alive but unreachable indefinitely.
- **Fix:** unconditional `millis() >= PERIODIC_RESTART_MS` check at the top of `loop()` (default 23h, overridable via `RETERMINAL_PERIODIC_RESTART_MS` in `platformio.local.ini`). `millis()` advances regardless of network state — no condition the zombie state can bypass. Also removed `WiFi.setAutoReconnect(true)` which raced with the manual reconnect logic in `maintainWifi()`. New capability field `periodic_restart_ms` confirms the threshold is armed. All 4 slots persist through the restart via LittleFS; display recovers transparently.
- **Evidence:** flashed May 5 2026 12:44:36; `/capabilities` reports `periodic_restart_ms: 82800000`, `loop_watchdog_armed: true`, `wifi_connected: true`, all 4 slots loaded, `reset_reason: poweron`, `self_restart_count: 0`.
- **Note:** `platformio.local.ini` is gitignored and must be created per-machine from `platformio.local.example.ini` before building. Missing local config was the cause of the intermediate no-credentials flash during this session.

## 2026-05-05 — Kitchen-display safety net + parsers lifted into `reterminal.family`

- **Symptoms:** when the upstream calendar heartbeat got blocked (OC exec-approval gate denied `gws calendar events list`) the panel kept showing yesterday's `calendar.md` for ~36h with no visible signal that the writer had died. Authoring errors in any of the four markdown sources (typos in time prefixes, malformed ISO dates, unknown mission `kind:` values) silently disappeared from the render with no error anywhere — the line just didn't show up. The four parsers were also locked inside `reterminal.providers.*`, so non-display tools (briefs, recall CLIs, OC flows) could not read family state without dragging in PIL/render dependencies.
- **Fix:** `render.kitchen.draw_source_stamp` now takes a per-provider `stale_after: timedelta` and renders a black `STALE` pill in the bottom-right corner when a source file's mtime exceeds threshold (calendar 2h, missions 3d, events/activities 14d). New `reterminal lint --feed <manifest>` walks every manifest-listed file with the same regexes the parsers use and reports lines the renderers would silently drop, exiting non-zero so it can gate authoring. New `reterminal.family.{calendar,missions,events,activities}` is the pure parsing layer (markdown → frozen dataclasses, no PIL); providers slimmed to render + `SceneProvider` and import from there. SHA256-pinned snapshot tests for all four renderers (`tests/test_renderer_snapshots.py`, goldens under `tests/fixtures/`) catch silent layout drift; the snapshot module gates on `HELVETICA.exists()` so it skips on Linux CI where the renderer falls back to PIL's default bitmap font and pixels would never match macOS goldens. Calendar render also strips Unicode pictographs from labels at render time so emoji-prefixed exporter output (e.g. `🏟️ Baseball`) doesn't render as tofu boxes.
- **Evidence:** `uv --directory python run --extra dev pytest -q` passes (`104 passed`), ruff clean, CI green on `df6723f` in 2m23s. `reterminal lint --feed examples/kitchen-display.local.json` returns `OK: no lint issues across 4 source(s)` against live `~/madad/family/`. After OC's `gws` allowlist was added (operational, OC-side, not in this repo), the heartbeat refresh ran successfully on its next session, `calendar.md` updated to `2026-05-05 16:17 EDT`, FSEvents → publisher pushed slot 0 to the device, and the STALE pill cleared. Downstream `reterminal.family` API verified end-to-end against real family files: 4 today, 3 tomorrow, 4 missions, 6 upcoming events with `days_until`, 3 recent + 3 queued activities.
- **Operational pointer (out of repo scope):** when slot 0 shows STALE for hours with the heartbeat process alive, check `~/.openclaw/exec-approvals.json` for a `gws` allowlist entry under `agents.*.allowlist`. The `gateway.log` line `denied by exec approval timeout / allowlist miss` against `gws calendar events list` is the canonical signature.

## 2026-05-04 — Kitchen ownership is manifest-first and legacy fixed pages are removed

- **Symptoms:** layout ownership still had multiple weaker truths: preview scripts hardcoded local content paths, kitchen providers hardcoded physical slots, `include_system` made manifest doctor/publish report an extra scene, the old fixed-page package still suggested a 7-page app model, destructive probe upload lacked the common `--live` guard, and local firmware config could carry a stale `RETERMINAL_BUILD_SHA`.
- **Fix:** make provider manifests own content paths and `slot: 0..3` pins; make previews resolve the same local/public manifest as the watcher; default `include_system` off; apply manifest slot pins outside provider code; move shared kitchen drawing helpers under `render/`; remove `python/reterminal/pages/*`; require `--live` for `probe --upload-pages`; inject git build SHA from a PlatformIO extra script instead of local config.
- **Evidence:** `uv --directory python run --extra dev pytest -q` passes (`85 passed`), `uv --directory python run --extra dev ruff check reterminal tests examples` passes, `platformio run -e reterminal` passes and prints `reTerminal build_sha=<checkout>-dirty`, USB flash succeeds, `doctor --feed examples/kitchen-display.local.json` reports `firmware_match: match` with 4 scenes/4 assignments, preview scripts render expected slot PNGs, manifest preview assigns `calendar/missions/events/activities` to slots `0/1/2/3`, and the sanitized destructive probe report was regenerated from the May 4 firmware.

## 2026-05-04 — Wi-Fi liveness now escalates on-device instead of relying on host retries

- **Symptoms:** the kitchen display could still become unreachable after long uptime even though the host watcher kept retrying and the loop-task watchdog was present.
- **Root cause:** the previous hardening only rebooted a blocked `loop()`. A device that was still looping but stuck in Wi-Fi reconnect attempts kept feeding the watchdog forever, so the host saw the same stale ePaper image and unreachable HTTP API until external power recovery.
- **Fix:** treat sustained Wi-Fi loss as a firmware health failure: configure STA mode with Wi-Fi sleep disabled, reset mDNS/OTA service state on link loss, retry normally during a grace window, then perform a controlled `ESP.restart()` after `RETERMINAL_WIFI_SELF_RESTART_MS` (default 10 min). `/capabilities` now reports Wi-Fi down duration, self-restart threshold, self-restart reason/count, and loop-watchdog arm status. Watchdog setup now still attempts to subscribe `loopTask` if the ESP framework already initialized the watchdog.
- **Evidence:** source-level regression coverage updated for the new capability fields; USB flash succeeded on the live unit and `/capabilities` reports `WiFi Down`, `Self Restarts`, `Last Self Restart`, and `Loop Watchdog: armed`. Final closure still requires a 48–72h soak on the flashed unit.

## 2026-05-01 — Live updater became DHCP-safe, curl-backed, and persistence-verified

- **Symptoms:** the launchd watcher had a stale fixed host, Python `requests` could not reach the device even when `curl` worked, firmware provenance was ambiguous, and after USB flash the device reported volatile slots because LittleFS failed to mount/format.
- **Root cause(s):** local launchd state pinned an old DHCP lease; host tooling trusted `requests` despite this macOS route failure mode; `doctor` did not compare firmware build SHA to the checkout; firmware mounted LittleFS without the partition label used by `partitions-32mb.csv`.
- **Fix:** remove the fixed local host, make the wrapper wait/retry discovery, make live publish rediscover on connection failures, add curl fallback for CLI/discovery HTTP operations, add firmware/build SHA comparison (including dirty builds), make doctor understand provider manifests, and mount LittleFS with the `littlefs` partition label.
- **Evidence:** USB flash succeeded; serial boot shows `LittleFS ready`, `Loaded slot 0..3 from flash`, `Restored 4 slots from flash`; `/capabilities` reports 4 loaded slots, LittleFS total/used bytes, `build_sha` matching the dirty checkout, and `firmware_match: match`; launchd watcher is running and seeded 4 slot digests from snapshots; tests pass (`80 passed`), ruff passes, `platformio run -e reterminal` and USB upload pass.

## 2026-05-01 — Public repo hygiene moved live/local state behind ignored overrides

- **Symptoms:** public docs and tracked helper files included machine-specific paths, DHCP leases, local content roots, serial suffixes, personal/family names, and live snapshot images. This confused agents and made the public repo harder to reuse safely.
- **Root cause:** operational state had accreted directly into public examples and docs as the kitchen display was debugged live.
- **Fix:** add `docs/access.md`; replace the tracked launchd plist with `scripts/sh.reterminal.publish.example.plist`; ignore local plists, local provider manifests, `.claude/`, and live snapshots; move example content roots to `~/reterminal-content/family`; sanitize probe/docs/tests; make the wrapper prefer an ignored `kitchen-display.local.json` when present.
- **Evidence:** sensitive-ref scans over tracked/public files return clean; `uv --directory python run --extra dev pytest -q` passes (`72 passed`), ruff passes, `plutil -lint scripts/sh.reterminal.publish.example.plist` passes, and `bash -n scripts/reterminal-publish-watch.sh` passes.

## 2026-04-28 — Publish defaults now avoid gratuitous visible refreshes

- **Symptoms:** `publish --push` selected slot 0 after every single-shot publish, even when uploads were unchanged or only hidden slots changed. Because `/page` performs a full refresh, this could flash the visible panel for no content change.
- **Root cause:** publishing conflated cache mutation with visible-page selection. The efficient path is staging hidden slots unless the caller explicitly asks to change what is on screen.
- **Fix:** `DisplayPublisher.publish()` now preserves the current visible slot by default and only calls `show_slot()` when `--show-slot` is provided. The live watcher also refreshes device capabilities every tick and clears/reseeds its digest cache if device uptime resets.
- **Evidence:** `uv run --extra dev pytest -q` passes (`72 passed`), ruff passes, preview scripts render, and `platformio run` succeeds for both firmware environments.

## 2026-04-27 — Review-task sweep made the live pipeline retry-safe and DHCP-safe

- **Symptoms:** review found several operational footguns: launchd pinned one DHCP lease, the live loop could mark a bitmap digest current before upload success, watcher restarts repushed already-cached slots, and interval examples encouraged unnecessary visible full refreshes.
- **Root cause(s):** production ownership had moved from bash polling to `publish --watch`, but docs and launchd still carried assumptions from the earlier loop. The in-memory cache represented "rendered" rather than "confirmed on device."
- **Fix:** add `scripts/reterminal-publish-watch.sh` discovery wrapper; make `run_live` seed slot hashes from `/snapshot` and mark cache entries only after successful `push_pil`; decommission legacy `refresh` / `watch` docs; update production docs to prefer `--watch` over `--interval`.
- **Evidence:** `uv run --extra dev pytest -q` passes (`68 passed`), ruff passes, `plutil -lint scripts/sh.reterminal.publish.example.plist` passes, and `bash -n scripts/reterminal-publish-watch.sh refresh.sh` passes. Live device restart/soak still needs verification after deployment.

## 2026-04-27 — Firmware source now rejects duplicate uploads cheaply and reports health

- **Symptoms:** host-side hashing avoids many redundant uploads, but dumb clients could still rewrite LittleFS and full-refresh the visible slot with byte-identical payloads; diagnosing Wi-Fi/storage/display state still required serial logs.
- **Root cause(s):** `/imageraw` always copied and persisted target-slot payloads before checking equality, and `/capabilities` exposed the display contract but not enough operational health.
- **Fix:** firmware no-ops unchanged stored uploads with `{skipped:true}`; adds reset reason, Wi-Fi reconnect counters, mDNS/OTA readiness, PSRAM, and LittleFS usage fields; starts mDNS and OTA on reconnect; at that point stopped auto-formatting LittleFS on ordinary mount failure; adds 32MB board/partition config. The LittleFS mount policy was later superseded on 2026-05-01 by mounting the labeled partition with auto-format for first-boot recovery.
- **Evidence:** `platformio run` succeeds for both `reterminal` and `ota`; build output now identifies `reTerminal E1001 ESP32S3 (32MB flash)`. Live flash/probe not run in this pass.

## 2026-04-27 — Kitchen provider previews now share production renderers

- **Symptoms:** preview scripts duplicated the provider parsing/rendering code, so previews could drift from what `publish --watch` actually pushed. Empty/missing markdown sources could also leave stale live slot content.
- **Root cause:** preview scripts predated provider-native prerendered scenes, and missing markdown returned no scene instead of an explicit visible state.
- **Fix:** preview scripts now call the production providers; providers share cached kitchen font helpers, render source-mtime stamps, and render explicit missing/empty states instead of silently preserving stale content.
- **Evidence:** `uv run python examples/preview_missions.py` and `uv run python examples/preview_family.py` wrote `/tmp/reterminal-review/slot-*.png`; provider tests pass in the 68-test suite.

## 2026-04-27 — Device froze after 24-48h of operational use; required power cycle

- **Symptoms:** kitchen display became unreachable on `/status` after 1-2 days of continuous operation. Power cycle restored normal operation. Pattern repeated.
- **Root cause(s):** two compounding firmware issues. (1) `WiFi.begin()` was called once in `setup()` with no reconnect logic in `loop()`, so an AP reboot or DHCP-lease renewal left the device silently off-network until physically power-cycled — the typical 24h DHCP cycle on home routers is the smoking gun. (2) Long ePaper paint loops (`do { } while (display.nextPage())`) starved the IDLE task during the 2-4s full refresh on the 800x480 panel, risking Task Watchdog Timer fires once SPI/UC8179 timing drifted under sustained use.
- **Fix:** firmware patch (commit `3dd5b14`): non-blocking `maintainWifi()` in `loop()` with 30s grace + 30s retry backoff calling `WiFi.disconnect()` + `WiFi.begin()`; `delay(1)` added inside every paint `do { }` body to feed the IDLE task. Six paint sites patched (`showPage`, `showBootScreen`, `showReadyScreen`, `showConfigRequiredScreen`, `showBlankScreen`, `/imageraw` direct path).
- **Evidence:** flashed via `/dev/cu.usbserial-*`, build sha `wifi-twdt-1`, 2026-04-27 09:07:27. Device back up immediately, all 4 slots restored from LittleFS, `free_heap` 222KB. 72h soak in progress.
- **Wrong diagnosis ruled out:** initial automated audit flagged an `imageBuffer` "leak" at `firmware/src/main.cpp:486` — but the allocation is guarded by `if (imageBuffer == nullptr)`, so it is a one-shot singleton, not a per-request leak. Confident wrong answer; verify before acting.
- **OTA gotcha (still recurring, see 2026-04-23 entry):** OTA flash from this Mac fails with "Host Not Found" because macOS Application Firewall drops the UDP reply from the device to espota's ephemeral port. USB flash via `/dev/cu.usbserial-*` works. Either disable firewall briefly or whitelist Python.

## 2026-04-24 — Designed kitchen slots were overwritten because live ownership was split between docs and a legacy refresh wrapper

- **Symptoms:** after the designed reTerminal pages landed, the device later showed the old routine/need/reset pages instead of the four-kid missions, upcoming-events, and activities/movie pages.
- **Root cause:** slot ownership was contradictory. `CLAUDE.md` still described legacy `ready-board` / `need-board` / `reset-board` as the live layout, while the skill doc said the designed pages were only preview-lifespan. The hourly the local legacy refresh wrapper rendered the legacy live feed for all four slots, so it silently overwrote slots 1-3 on the next refresh.
- **Fix:** make slot ownership explicit and durable: slot 0 remains the calendar/feed page; slots 1-3 are the designed markdown-driven pages from `~/reterminal-content/family/{missions,events,activities}.md`. Added `docs/kitchen-display-sop.md`, updated `CLAUDE.md`, updated the agent reTerminal instructions, and patched the refresh wrapper to overlay slots 1-3 from `preview_missions.py` / `preview_family.py` before publishing raws.
- **Evidence:** `uv run --extra dev pytest -q` passes (`42 passed`), `uv run --extra dev ruff check reterminal tests` passes, production refresh reports no slot drift, and device `/snapshot` hashes for slots 1-3 match the local designed raw files exactly.
- **Gotcha (recurring):** a pretty manual push is not production unless the unattended refresh loop is taught the same ownership. Any future slot-layout change must update `CLAUDE.md`, this log/SOP, the agent instructions, and the refresh path together.

## 2026-04-23 — Ghosting fixed: full refresh on every path, plus hibernate everywhere

- **Symptoms:** display showed ghosting, washed-out contrast, and artifacted afterimages after the hourly feed had run for a while.
- **Root cause(s):** two compounding issues. (1) The 2026-04-17 partial-only policy was correct for the minute-cadence architecture that existed then but became a liability under the current hourly feed. (2) The firmware never called `display.hibernate()` after refresh cycles, so the UC8179 controller left panel driving voltages on between updates, contributing to residual charge — a deviation from the GxEPD2 canonical example.
- **Two false starts before the right answer:**
  - Attempt 1 flipped the default to "full refresh on every update." Fixed the ghost, but every L/R button press flashed for ~2s. Felt punishing.
  - Attempt 2 split the policy: full refresh on content change (push, right button, boot), partial refresh on navigation (/page switch, L/M buttons). Reasoning was the Kindle pattern — partial between already-rendered content. This produced **worse** artifacting on nav: dithered/layered ghosts where previous-slot content bled through into the next. The Kindle analogy was wrong because Kindle page turns are mostly the same layout with small text differences; these 4 slots are completely dissimilar layouts (agenda vs routine list vs grocery vs reset), and the partial LUT can't handle large pixel deltas cleanly on this panel.
- **Final fix:** full refresh on every path — push, navigation, buttons, boot. `showPagePartial` removed entirely. Every refresh function ends with `display.hibernate()`. The ~2s flash on nav is the accepted cost for having information display quality across dissimilar slots.
- **Evidence:** before any firmware change, three `POST /page?full=1` calls in sequence produced the cleanest display in recent memory — refuting the 2026-04-17 claim that full refresh inherently degrades typography. Final firmware flashed via USB (CH340 at `/dev/cu.usbserial-*`, build `Apr 23 2026 10:11:46`). Navigation between slots is clean; content push lands clean.
- **Gotcha (recurring):** the 2026-04-17 entry below is still instructive — at minute-or-faster cadence, repeated full refreshes accumulate contrast loss faster than the substrate can settle. The rule is cadence-aware. Partial refresh is the right tool only when the content being updated is *incremental on the same layout* (e.g. a ticking clock in a fixed position over otherwise static chrome), not for whole-page swaps.
- **OTA gotcha:** OTA flash from this Mac fails with "Host Not Found" despite the device advertising `_arduino._tcp`. Diagnosis: macOS Application Firewall drops the UDP reply from the device to espota's ephemeral port. USB flash via `/dev/cu.usbserial-*` works reliably. To fix OTA, either allow Python through macOS firewall or disable the firewall briefly for the flash.

## 2026-04-22 — Baseball rows became much more useful once the feed preserved practice/game/team/opponent detail

- **Symptoms:** the common household question was whether baseball was a practice or a game, for which team, and against whom — but the earlier simplified schedule collapsed too much of that detail into generic `Baseball` labels.
- **Root cause:** schedule titles were being normalized too aggressively for the display, which removed exactly the distinctions the kitchen board needed to preserve.
- **Fix:** keep baseball-specific detail in the feed (`NSMS Practice`, `Team Practice`, `Team vs Opponent`, `Team vs Opponent`), add practice/game icon variants, and prioritize baseball rows on the main Today/Tomorrow board before pushing lower-priority overflow elsewhere.
- **Evidence:** current live/previews show tomorrow baseball entries with practice/game/team/opponent detail intact, while non-baseball overflow is deprioritized.

## 2026-04-22 — Kitchen pages got more useful once they shifted from generic family summaries to action pages

- **Symptoms:** the kitchen display still had a low-value upcoming page and a chores page that was just placeholder kid labels instead of the actual routine the family follows.
- **Root cause:** the page model was still organized around abstract categories instead of the real kitchen workflow: today/tomorrow, routine, need, and reset.
- **Fix:** replace the old upcoming page with a reset page, populate `chores.md` with the real after-school and cleanup routine, and keep the main board focused on today/tomorrow baseball-aware schedule plus dinner.
- **Evidence at the time:** previews/live slots were `today-board`, `ready-board`, `need-board`, and `reset-board`, with routine lines like unpack backpack / reading / work and reset lines like dishes / laundry / vacuum / tabletops. This layout was later superseded on 2026-04-24 by the designed missions/events/activities slots.

## 2026-04-22 — Kitchen schedule became much clearer once calendar data was rendered as structured agenda rows instead of raw event strings

- **Symptoms:** the kitchen display needed bigger chunks and clearer ownership cues than a generic family-summary layout or raw Google Calendar strings could provide.
- **Root cause:** the earlier scene model compressed schedule data into plain text lines, which made it hard to compare today vs tomorrow and hard to see which kid or family group owned each event.
- **Fix:** add an `agenda` scene kind with structured rows (owner chip, event icon, time, title), switch slot 0 to a two-column Today/Tomorrow board with dinner, add a grouped upcoming agenda for later days, and move chores / meal-prep into dedicated kitchen pages.
- **Evidence at the time:** previews and the live device showed `today-board`, `ready-board`, `need-board`, and `upcoming-board`, with event ownership indicated by `A/H/L/N/F` chips and custom 1-bit icons. This layout was later superseded on 2026-04-24 by the designed missions/events/activities slots.

## 2026-04-22 — Text-heavy scenes looked choppy because the renderer treated typography like dithered art

- **Symptoms:** body copy on the device looked dot-matrix-like, ellipsized too aggressively, and still carried too much chrome for a kitchen-family display.
- **Root cause:** the renderer was using the same Floyd-Steinberg output style and generic dashboard-ish layout pressure for text scenes that should have behaved more like calm posters or lists.
- **Fix:** render non-poster scenes with a hard threshold instead of dithering, add chrome-free `focus` heroes plus quieter list pages, and move the live family feed toward one focus page plus short 4-item lists.
- **Evidence:** current previews show cleaner threshold-rendered text, and the newer kitchen agenda/list pages keep larger rows with less forced truncation.

## 2026-04-22 — Host refresh loop was redrawing the visible slot on every hidden-slot update

- **Symptoms:** the display would look stuck or heavily ghosted after running for a day or two, even when the user stayed on a mostly static page like the family calendar.
- **Root cause:** the local legacy refresh wrapper called `POST /page` for the current slot whenever *any* slot changed. At the same time, the old feed changed slot 0 every minute (clock) and slot 1 frequently (ops timestamp), so the visible page was being partially refreshed thousands of extra times. The live log showed `showing slot` about 2,695 times, while slot 2 only uploaded 34 times and slot 3 only 19 times.
- **Fix:** change the bridge to redraw the screen only when the currently visible slot changed, when the device rebooted, or when the current slot was not loaded. Rework the live feed toward lower-churn family/kitchen scenes instead of minute-by-minute ops pages.
- **Evidence:** after the change, the bridge can distinguish hidden-slot-only updates from visible-slot updates, and the family feed no longer needs minute-by-minute clock/ops pages to stay useful.

## 2026-04-17 — Helvetica Neue degraded ePaper typography; reverted to Helvetica

- **Symptoms:** after switching sans font from Helvetica to Helvetica Neue, text on the ePaper display had inconsistent stroke widths — thin strokes broke up or disappeared after Floyd-Steinberg 1-bit dithering.
- **Root cause:** Helvetica Neue has thinner stroke weights than Helvetica. At small sizes, the thin/thick contrast falls across the dithering threshold unevenly, producing inconsistent line widths on 1-bit output.
- **Fix:** reverted font priority in `fonts.py` to prefer `/System/Library/Fonts/Helvetica.ttc` (uniform stroke weight). Helvetica Neue removed from the list.
- **Evidence:** re-rendered previews with Helvetica show clean, consistent strokes at all sizes.
- **Gotcha (recurring):** for 1-bit monochrome ePaper, prefer fonts with uniform stroke weight. Avoid neo-grotesque variants with optical size adjustments — they fight the dithering.

## 2026-04-17 — Full ePaper refresh degrades display quality vs partial refresh

- **Symptoms:** after a full refresh (black→white→content), typography and line weights looked visibly worse than partial refresh updates.
- **Root cause:** full ePaper refresh drives all pixels through a complete inversion cycle which introduces slight contrast loss. Partial refresh updates pixels in place with higher fidelity.
- **Fix:** firmware changed to use partial refresh exclusively for all API-driven updates. Full refresh only triggers on right button press or `POST /page` with `?full=1`. Removed the automatic full-refresh-every-N-partials counter.
- **Evidence:** after flashing, partial-only updates maintain consistent typography quality across cycles.

## 2026-04-16 — Family calendar blank because naive datetime fails Google Calendar API

- **Symptoms:** family-calendar scene on the reTerminal showed "calendar unavailable" or empty items despite valid GWS auth.
- **Root cause:** `generate_reterminal_feed.py` passed `datetime.now().isoformat()` (e.g. `2026-04-16T15:30:00.123456`) as `timeMin`/`timeMax`. Google Calendar API requires RFC3339 with timezone info — naive timestamps return 400 Bad Request.
- **Fix:** use `now.astimezone(timezone.utc).isoformat()` to produce `2026-04-16T19:30:00+00:00`.
- **Evidence:** after the fix, `generate_reterminal_feed.py` produced a feed with 5 family events (calendar events, etc.) via the local file-auth path.

## 2026-04-16 — GWS credentials wiped by macOS Keychain failure in headless context

- **Symptoms:** `gws calendar +agenda` returned 401 "No credentials provided" for some local profiles, while another was never authed.
- **Root cause:** GWS 0.22.3 made macOS Keychain the strict default. In headless/agent contexts (tmux, SSH, subprocess), Keychain prompts for user interaction and fails. On failure, GWS **deletes** the encrypted credentials file as "undecryptable."
- **Fix:** (1) Set `GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file` in the `gws-account` wrapper so all calls use file-based AES-256 encryption. (2) Re-auth all four profiles. (3) Updated GWS skill docs to document the requirement.
- **Evidence:** all local profiles verified with `token_valid: true` and `gws-account <profile> calendar +agenda --today` returns full calendar data headlessly.

## 2026-04-16 — Bridge host detection broke after reflash because `/status` schema changed

- **Symptoms:** the local legacy refresh wrapper reported the device unavailable after the USB reflash even though `curl http://<device-ip>/status` succeeded.
- **Root cause:** the bridge scripts validated only the older firmware field `page_name`; the reflashed firmware reports `current_page_name`.
- **Fix:** update the bridge discovery checks to accept either `page_name` or `current_page_name`, and export `SUBNET_PREFIX` into the parallel subnet scan shells.
- **Evidence:** after the fix, the local legacy refresh wrapper rediscovered `<device-ip>`, republished all 4 slots, and the tmux loop returned to `changed_slots=0` when nothing had changed.

## 2026-04-16 — Reflashed firmware failed Wi-Fi because the local SSID override used the wrong case

- **Symptoms:** after a successful USB flash, serial boot logs stalled at `Connecting to WiFi.....` and then reported `WiFi failed!`, leaving the device off-network.
- **Root cause:** `firmware/platformio.local.ini` built `RETERMINAL_WIFI_SSID="<wrong-case-ssid>"` while the live SSID requires the configured case.
- **Fix:** change the local override to uppercase `<ssid>`, clean rebuild, and flash again over USB.
- **Evidence:** the next boot log showed `Connected! IP: <device-ip>`, `HTTP server started`, and `OTA ready`, and live `GET /capabilities` / `GET /snapshot` succeeded.

## 2026-04-16 — USB serial interrogation on a macOS host turned network guesswork into verified hardware truth

- **Symptoms:** network-only debugging left the board identity, flash size, and exact firmware state ambiguous.
- **Root cause:** the reliable source of truth on a macOS host was the USB serial path, but earlier attempts used either a charge-only cable or no working data path.
- **Fix:** switch to a working USB data cable, use the `CH340` serial bridge at `/dev/cu.usbserial-*`, interrogate the bootloader with `esptool.py read_mac` / `flash_id`, then capture serial boot logs and flash from `firmware/`.
- **Evidence:** bootloader interrogation identified `ESP32-S3 (QFN56) v0.2`, embedded `8MB` PSRAM, `32MB` flash, and the reflashed device later returned live `/capabilities` plus byte-for-byte `/snapshot` readback.

## 2026-04-02 — Local PlatformIO overrides could recurse on `build_flags`

- **Symptoms:** copying the local firmware override pattern directly caused PlatformIO to fail with an infinite-recursion error for `build_flags`.
- **Root cause:** the local override reused `${env:reterminal.build_flags}` in a way that recursed once loaded through `extra_configs`.
- **Fix:** inline the base firmware build flags in `platformio.local.ini` when preparing a real local flash config.
- **Evidence:** replacing the recursive override with literal base flags restored successful local firmware builds.

## 2026-04-02 — Flashed firmware lagged behind tracked source and reboot exposed volatile cache behavior

- **Symptoms:** the live device still showed `Page 1/4`, `/capabilities` returned `404`, `/clear` returned `404`, and a power cycle came back with `loaded: false` until the host republished.
- **Root cause:** the physical device was still running an older flashed firmware even though the repo source had already moved to neutral slot names, richer capabilities, and no overlay chrome.
- **Fix:** keep treating the current hardware as an older 4-slot volatile-cache build until a reflash succeeds; wire the host to fall back gracefully and preserve the reboot-detect-and-republish path.
- **Evidence:** live checks on `<device-ip>` showed `GET /page` with `loaded: false` after reboot and `404` responses for `/capabilities` / `/clear`, while the updated source built successfully locally.

## 2026-04-01 — Firmware overlay chrome was fighting host-rendered pages

- **Symptoms:** even after host-side renderer changes removed folios, the live device still showed `Page 1/4` at the bottom of the screen.
- **Root cause:** the flashed firmware overlaid a page indicator inside `showPage()` after drawing the uploaded bitmap.
- **Fix:** remove the firmware overlay, switch tracked slot names to neutral `slot-0..slot-3`, and add a richer `/capabilities` endpoint plus `/clear` for truthful host control.
- **Evidence:** source inspection in `firmware/src/main.cpp` showed the overlay string construction; the tracked firmware now builds successfully without that code.

## 2026-04-01 — Device looked stuck because network identity and visible-slot behavior drifted

- **Symptoms:** the screen appeared stuck on old content, historical DHCP addresses were unreliable, and a successful upload did not necessarily change what the user saw.
- **Root causes:** stale DHCP assumptions, static demo feed confusion, and push flows that uploaded content without explicitly selecting a visible slot.
- **Fix:** require explicit host/discovery in the Python CLI, add `reterminal discover` / `reterminal doctor`, push a visible slot after publish, and guard legacy fixed pages against targeting slots beyond the verified 4-slot device.
- **Evidence:** live recovery session rediscovered the device at `<device-ip>`, uploaded all four scene slots, and confirmed `GET /page` with `loaded: true` while the user could manually navigate the refreshed pages.

## 2026-04-01 — local bridge needed a curl-based transport on a macOS host

- **Symptoms:** local bridge scripts sometimes saw Python HTTP calls fail with `OSError(65, 'No route to host')` while plain `curl http://<host>/status` worked against the same device.
- **Fix:** make the local bridge use `curl` for host discovery and device HTTP operations, validate `/status` responses as reTerminal-shaped JSON, preserve the currently visible slot during refresh, and skip unchanged slot uploads with reboot-aware hash invalidation.
- **Evidence:** the local legacy refresh wrapper successfully discovered `<device-ip>`, pushed scene slots, preserved the user-selected page, and subsequent refreshes reported `changed_slots=0` when nothing had changed.
