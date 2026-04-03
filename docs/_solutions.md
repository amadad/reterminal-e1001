# Solutions log

Newest first. Keep entries short, dated, and evidence-oriented.

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
