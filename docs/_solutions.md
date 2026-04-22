# Solutions log

Newest first. Keep entries short, dated, and evidence-oriented.

## 2026-04-22 — Baseball rows became much more useful once the feed preserved practice/game/team/opponent detail

- **Symptoms:** the boys' biggest question was whether baseball was a practice or a game, for which team, and against whom — but the earlier simplified schedule collapsed too much of that detail into generic `Baseball` labels.
- **Root cause:** schedule titles were being normalized too aggressively for the display, which removed exactly the distinctions the kitchen board needed to preserve.
- **Fix:** keep baseball-specific detail in the feed (`NSMS Practice`, `Orioles Practice`, `Orioles vs Angels`, `Pirates vs Rockies`), add practice/game icon variants, and prioritize baseball rows on the main Today/Tomorrow board before pushing lower-priority overflow elsewhere.
- **Evidence:** current live/previews show tomorrow baseball entries with practice/game/team/opponent detail intact, while non-baseball overflow is deprioritized.

## 2026-04-22 — Kitchen pages got more useful once they shifted from generic family summaries to action pages

- **Symptoms:** the kitchen display still had a low-value upcoming page and a chores page that was just placeholder kid labels instead of the actual routine the family follows.
- **Root cause:** the page model was still organized around abstract categories instead of the real kitchen workflow: today/tomorrow, routine, need, and reset.
- **Fix:** replace the old upcoming page with a reset page, populate `chores.md` with the real after-school and cleanup routine, and keep the main board focused on today/tomorrow baseball-aware schedule plus dinner.
- **Evidence:** current previews/live slots are `today-board`, `ready-board`, `need-board`, and `reset-board`, with routine lines like unpack backpack / reading / work and reset lines like dishes / laundry / vacuum / tabletops.

## 2026-04-22 — Kitchen schedule became much clearer once calendar data was rendered as structured agenda rows instead of raw event strings

- **Symptoms:** the kitchen display needed bigger chunks and clearer ownership cues than a generic family-summary layout or raw Google Calendar strings could provide.
- **Root cause:** the earlier scene model compressed schedule data into plain text lines, which made it hard to compare today vs tomorrow and hard to see which kid or family group owned each event.
- **Fix:** add an `agenda` scene kind with structured rows (owner chip, event icon, time, title), switch slot 0 to a two-column Today/Tomorrow board with dinner, add a grouped upcoming agenda for later days, and move chores / meal-prep into dedicated kitchen pages.
- **Evidence:** current previews and the live device now show `today-board`, `ready-board`, `need-board`, and `upcoming-board`, with event ownership indicated by `A/H/L/N/F` chips and custom 1-bit icons.

## 2026-04-22 — Text-heavy scenes looked choppy because the renderer treated typography like dithered art

- **Symptoms:** body copy on the device looked dot-matrix-like, ellipsized too aggressively, and still carried too much chrome for a kitchen-family display.
- **Root cause:** the renderer was using the same Floyd-Steinberg output style and generic dashboard-ish layout pressure for text scenes that should have behaved more like calm posters or lists.
- **Fix:** render non-poster scenes with a hard threshold instead of dithering, add chrome-free `focus` heroes plus quieter list pages, and move the live family feed toward one focus page plus short 4-item lists.
- **Evidence:** current previews show cleaner threshold-rendered text, and the newer kitchen agenda/list pages keep larger rows with less forced truncation.

## 2026-04-22 — Host refresh loop was redrawing the visible slot on every hidden-slot update

- **Symptoms:** the display would look stuck or heavily ghosted after running for a day or two, even when the user stayed on a mostly static page like the family calendar.
- **Root cause:** `~/oc-min/scripts/reterminal-refresh.sh` called `POST /page` for the current slot whenever *any* slot changed. At the same time, the old feed changed slot 0 every minute (clock) and slot 1 frequently (ops timestamp), so the visible page was being partially refreshed thousands of extra times. The live log showed `showing slot` about 2,695 times, while slot 2 only uploaded 34 times and slot 3 only 19 times.
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
- **Evidence:** after the fix, `generate_reterminal_feed.py` produced a feed with 5 family events (Hasan Plant, Baseball, Quran, etc.) via `family-profile/file` auth path.

## 2026-04-16 — GWS credentials wiped by macOS Keychain failure in headless context

- **Symptoms:** `gws calendar +agenda` returned 401 "No credentials provided" for ali-givecare, and amadad was never authed.
- **Root cause:** GWS 0.22.3 made macOS Keychain the strict default. In headless/agent contexts (tmux, SSH, subprocess), Keychain prompts for user interaction and fails. On failure, GWS **deletes** the encrypted credentials file as "undecryptable."
- **Fix:** (1) Set `GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file` in the `gws-account` wrapper so all calls use file-based AES-256 encryption. (2) Re-auth all four profiles. (3) Updated GWS skill docs to document the requirement.
- **Evidence:** all four profiles (amadad, ali-givecare, ali-scty, agent) verified with `token_valid: true` and `gws-account amadad calendar +agenda --today` returns full calendar data headlessly.

## 2026-04-16 — Bridge host detection broke after reflash because `/status` schema changed

- **Symptoms:** `~/oc-min/scripts/reterminal-refresh.sh` reported the device unavailable after the USB reflash even though `curl http://192.168.7.32/status` succeeded.
- **Root cause:** the bridge scripts validated only the older firmware field `page_name`; the reflashed firmware reports `current_page_name`.
- **Fix:** update the bridge discovery checks to accept either `page_name` or `current_page_name`, and export `SUBNET_PREFIX` into the parallel subnet scan shells.
- **Evidence:** after the fix, `~/oc-min/scripts/reterminal-refresh.sh` rediscovered `192.168.7.32`, republished all 4 slots, and the tmux loop returned to `changed_slots=0` when nothing had changed.

## 2026-04-16 — Reflashed firmware failed Wi-Fi because the local SSID override used the wrong case

- **Symptoms:** after a successful USB flash, serial boot logs stalled at `Connecting to WiFi.....` and then reported `WiFi failed!`, leaving the device off-network.
- **Root cause:** `firmware/platformio.local.ini` built `RETERMINAL_WIFI_SSID="horus"` while the live SSID is `HORUS`.
- **Fix:** change the local override to uppercase `HORUS`, clean rebuild, and flash again over USB.
- **Evidence:** the next boot log showed `Connected! IP: 192.168.7.32`, `HTTP server started`, and `OTA ready`, and live `GET /capabilities` / `GET /snapshot` succeeded.

## 2026-04-16 — USB serial interrogation on kunst turned network guesswork into verified hardware truth

- **Symptoms:** network-only debugging left the board identity, flash size, and exact firmware state ambiguous.
- **Root cause:** the reliable source of truth on `kunst` was the USB serial path, but earlier attempts used either a charge-only cable or no working data path.
- **Fix:** switch to a working USB data cable, use the `CH340` serial bridge at `/dev/cu.usbserial-1410`, interrogate the bootloader with `esptool.py read_mac` / `flash_id`, then capture serial boot logs and flash from `firmware/`.
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
- **Evidence:** live checks on `192.168.7.97` showed `GET /page` with `loaded: false` after reboot and `404` responses for `/capabilities` / `/clear`, while the updated source built successfully locally.

## 2026-04-01 — Firmware overlay chrome was fighting host-rendered pages

- **Symptoms:** even after host-side renderer changes removed folios, the live device still showed `Page 1/4` at the bottom of the screen.
- **Root cause:** the flashed firmware overlaid a page indicator inside `showPage()` after drawing the uploaded bitmap.
- **Fix:** remove the firmware overlay, switch tracked slot names to neutral `slot-0..slot-3`, and add a richer `/capabilities` endpoint plus `/clear` for truthful host control.
- **Evidence:** source inspection in `firmware/src/main.cpp` showed the overlay string construction; the tracked firmware now builds successfully without that code.

## 2026-04-01 — Device looked stuck because network identity and visible-slot behavior drifted

- **Symptoms:** the screen appeared stuck on old content, historical `.76/.77/.78` addresses were unreliable, and a successful upload did not necessarily change what the user saw.
- **Root causes:** stale DHCP assumptions, static demo feed confusion, and push flows that uploaded content without explicitly selecting a visible slot.
- **Fix:** require explicit host/discovery in the Python CLI, add `reterminal discover` / `reterminal doctor`, push a visible slot after publish, and guard legacy fixed pages against targeting slots beyond the verified 4-slot device.
- **Evidence:** live recovery session rediscovered the device at `192.168.7.97`, uploaded all four scene slots, and confirmed `GET /page` with `loaded: true` while the user could manually navigate the refreshed pages.

## 2026-04-01 — OpenClaw bridge needed a curl-based transport on kunst

- **Symptoms:** local bridge scripts sometimes saw Python HTTP calls fail with `OSError(65, 'No route to host')` while plain `curl http://<host>/status` worked against the same device.
- **Fix:** make the OpenClaw bridge use `curl` for host discovery and device HTTP operations, validate `/status` responses as reTerminal-shaped JSON, preserve the currently visible slot during refresh, and skip unchanged slot uploads with reboot-aware hash invalidation.
- **Evidence:** `~/oc-min/scripts/reterminal-refresh.sh` successfully discovered `192.168.7.97`, pushed scene slots, preserved the user-selected page, and subsequent refreshes reported `changed_slots=0` when nothing had changed.
