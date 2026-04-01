# Solutions log

Newest first. Keep entries short, dated, and evidence-oriented.

## 2026-04-01 — Device looked stuck because network identity and visible-slot behavior drifted

- **Symptoms:** the screen appeared stuck on old content, historical `.76/.77/.78` addresses were unreliable, and a successful upload did not necessarily change what the user saw.
- **Root causes:** stale DHCP assumptions, static demo feed confusion, and push flows that uploaded content without explicitly selecting a visible slot.
- **Fix:** require explicit host/discovery in the Python CLI, add `reterminal discover` / `reterminal doctor`, push a visible slot after publish, and guard legacy fixed pages against targeting slots beyond the verified 4-slot device.
- **Evidence:** live recovery session rediscovered the device at `192.168.7.97`, uploaded all four scene slots, and confirmed `GET /page` with `loaded: true` while the user could manually navigate the refreshed pages.

## 2026-04-01 — OpenClaw bridge needed a curl-based transport on kunst

- **Symptoms:** local bridge scripts sometimes saw Python HTTP calls fail with `OSError(65, 'No route to host')` while plain `curl http://<host>/status` worked against the same device.
- **Fix:** make the OpenClaw bridge use `curl` for host discovery and device HTTP operations, validate `/status` responses as reTerminal-shaped JSON, preserve the currently visible slot during refresh, and skip unchanged slot uploads with reboot-aware hash invalidation.
- **Evidence:** `~/oc-min/scripts/reterminal-refresh.sh` successfully discovered `192.168.7.97`, pushed scene slots, preserved the user-selected page, and subsequent refreshes reported `changed_slots=0` when nothing had changed.
