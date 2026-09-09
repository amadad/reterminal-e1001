# Firmware

ESP32-S3 deep-sleep pull firmware for reTerminal E1001.

Current tracked source is designed to stay small and truthful:

- host-rendered 1-bit bitmaps
- 4 slot buffers in PSRAM, persisted to LittleFS when storage is mounted
- timer-based HTTP pull plus a short-lived diagnostic API
- no firmware overlay chrome on stored pages
- neutral slot names (`slot-0..slot-3`) instead of semantic app page names

## Requirements

- [PlatformIO](https://platformio.org/install) (CLI or VS Code extension)
- USB-C cable for initial flash
- reTerminal E1001 device

## Install PlatformIO

```bash
# macOS/Linux
brew install platformio
# or
pip install platformio

# Verify installation
pio --version
```

## Configuration

### Local secrets and host overrides

Do **not** edit `src/main.cpp` with real credentials.

Instead, copy the example local config and keep the real file untracked:

```bash
cd firmware
cp platformio.local.example.ini platformio.local.ini
```

Then edit `platformio.local.ini`:

```ini
[env:reterminal]
build_flags =
    -DBOARD_HAS_PSRAM
    -DARDUINO_USB_CDC_ON_BOOT=1
    -DEPAPER_ENABLE
    -Iinclude
    -DRETERMINAL_WIFI_SSID=\"YourNetwork\"
    -DRETERMINAL_WIFI_PASS=\"YourPassword\"
    -DRETERMINAL_HOSTNAME=\"reterminal\"
    -DRETERMINAL_OTA_PASSWORD=\"set-a-real-password\"
    -DRETERMINAL_FIRMWARE_VERSION=\"local-dev\"

[env:ota]
upload_port = reterminal.local
```

Notes:

- Wi-Fi is now configured via build flags, not hardcoded in source.
- OTA is **disabled by default** and only starts when `RETERMINAL_OTA_PASSWORD` is set.
- Wi-Fi self-recovery restarts the firmware after a sustained post-boot outage
  (`RETERMINAL_WIFI_SELF_RESTART_MS`, default 600000 ms). Set it to `0` only for
  bench debugging when you want the device to stay wedged for inspection.
- Build SHA is injected automatically by `tools/git_build_flags.py`; do not hand-maintain `RETERMINAL_BUILD_SHA` in local config.
- `platformio.local.ini` is gitignored, but build flags can still appear in `pio project config` output; avoid pasting local config output into logs.
- The example file repeats the base build flags intentionally. Do not reference `${env:reterminal.build_flags}` from `platformio.local.ini`; PlatformIO can recurse when loading it as an `extra_config`.

## Flashing

For the full agent access contract, including USB-vs-HTTP boundaries and Python/uv path rules, see `../docs/access.md`.

### First Time (USB)

1. Connect reTerminal to your computer via USB-C
2. Discover the current serial path with `pio device list` (`/dev/cu.usbserial-*` or `/dev/cu.usbmodem*` on macOS; suffixes drift)
3. Put device in bootloader mode if needed (hold BOOT while connecting)
4. Flash:

```bash
cd firmware
pio run -e reterminal -t upload --upload-port /dev/cu.usbserial-XXXX
```

5. Monitor serial output:

```bash
pio device monitor -p /dev/cu.usbserial-XXXX -b 115200
```

You should see something like:
```
reTerminal E1001 Starting...
Allocating page storage...
Display initialized
Connecting to WiFi....
Connected! IP: 192.168.x.x
HTTP server started
OTA ready
Setup complete!
```

If Wi-Fi is not configured, the device now stops on a configuration screen instead of silently using baked-in credentials.

After a successful Wi-Fi boot, rediscover the current DHCP lease from the host side instead of assuming an old IP:

```bash
cd ..
env -u VIRTUAL_ENV uv --directory python run reterminal discover
env -u VIRTUAL_ENV uv --directory python run reterminal doctor --host <device-ip>
```

### Subsequent Updates (OTA)

Once the device is on Wi-Fi, flash wirelessly:

```bash
# Set upload_port in platformio.local.ini first
pio run -e ota -t upload
```

## Architecture

The firmware is a **deep-sleep + HTTP-pull client**. A timer wake (default
1800 seconds) or cold boot connects Wi-Fi and runs one bounded publish cycle:

1. Compute full SHA-256 hashes from slots loaded from LittleFS.
2. `GET <publisher>/content-hash` for the desired per-slot hashes. Explicit
   `null` means unassigned and preserves the cached slot; retiring content
   requires a replacement bitmap. Missing or malformed hashes are errors.
3. Fetch changed slots with `GET /content/slot-N?hash=<desired-sha256>`.
   Require exactly 48,000 bytes and a matching SHA-256. Response body reads
   have total deadlines (5 seconds for the bounded hash manifest, 10 seconds
   per bitmap), including when bytes arrive slowly. A publisher edition
   change during the download returns `409` and is retried on the next wake.
4. Write each candidate to a temporary LittleFS file, read it back to verify
   the bytes, and atomically rename it over the previous slot. Failed downloads
   or writes preserve the last good file and in-memory bitmap.
5. Fully refresh the selected page when any slot changed, then hibernate the
   display.
6. `POST <publisher>/receipt`, then return to deep sleep. Receipt failures are
   logged and never keep the device awake indefinitely.

Short button wakes navigate or redraw cached pages without connecting Wi-Fi.
An RTC deadline preserves the next scheduled pull through navigation wakes;
pressing a button no longer restarts the 30-minute countdown. This uses the
configured RTC-backed `gettimeofday()` clock, which persists through deep sleep
([ESP-IDF system time](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/system/system_time.html));
it does not require network time. A due pull wakes one second after the button
interaction. `next_poll_in_s` in status and receipts reports the remaining delay.
A long right-button hold pulls fresh content once before opening diagnostics.
Normal operation retains the 30-minute sleep interval; no always-on server or
additional dependency is required.

### Delivery receipts

`POST /receipt` sends versioned JSON with `schema_version: 1`, `device_id`
(Wi-Fi MAC), `hostname`, `firmware_version`, `build_sha`, `boot_count`,
`wake_reason` (`timer`, `diagnostic`, or `boot`), `wake_interval_s`,
`current_page`, `uptime_ms`, `battery_mv`, and `rssi`.

- `hashes` contains all four `slot-N` keys: SHA-256 of the verified persisted
  bytes, or `null` when unavailable. These are actual stored hashes, including
  unchanged slots, rather than a copy of the host's requested manifest.
- `outcome` is `updated`, `unchanged`, `partial`, or `error`; `error` is a stable
  reason or `null`, and `slot_errors` identifies failed slot downloads/writes.
- `refresh_returned` reports that the full-refresh driver call returned during
  this wake. `displayed_hash` identifies the bitmap submitted in the last such
  call, retained in RTC memory, or `null` when unknown. The driver can return
  after a busy timeout, so neither field proves controller success or optical
  appearance.

The host supplies the receipt timestamp; the device does not invent wall-clock
freshness. Missing receipts are detectable by the host, including Wi-Fi failures
that prevent any acknowledgment. These fields also appear in diagnostic
`GET /status`; the outcome is `not_attempted` until a pull has run in this wake.
The source implementation must be flashed and physically verified before these
fields can be claimed for an existing device.

### Diagnostic mode

Long-press the **right** button for 3 seconds (`RETERMINAL_DIAGNOSTIC_HOLD_MS`)
while waking from EXT1. The firmware brings up:

- `GET /status` — JSON: uptime, battery_mv, RSSI, free_heap, build SHA, slot state
- `GET /eventlog` — persistent ring buffer (boot, wake_timer, wake_button, diagnostic, wifi_fail, pull_updated, pull_unchanged, pull_partial, pull_error, receipt_fail)
- `GET /snapshot[?page=N]` — exact stored 48000-byte bitmap for inspection
- `POST /imageraw?page=N` — manual push (legacy; mostly unused)
- `GET/POST /page` — read or set the visible slot
- `POST /sleep` — return to deep sleep immediately
- mDNS advertising as `reterminal.local`
- OTA listener (if `RETERMINAL_OTA_PASSWORD` is set)

After `RETERMINAL_DIAGNOSTIC_TIMEOUT_MS` (default 10 min) the firmware
returns to deep sleep automatically. This is the path for OTA-flashing or
post-mortem inspection.

### Build flags

| Flag | Default | Purpose |
|---|---|---|
| `RETERMINAL_WIFI_SSID` / `_PASS` | — | WiFi credentials |
| `RETERMINAL_HOSTNAME` | `reterminal` | mDNS / hostname |
| `RETERMINAL_OTA_PASSWORD` | unset (OTA off) | Diagnostic-mode OTA |
| `RETERMINAL_PUBLISHER_HOST` | unset (no pull) | Host running the content server |
| `RETERMINAL_PUBLISHER_PORT` | 8765 | Content server port |
| `RETERMINAL_WAKE_INTERVAL_S` | 1800 (30 min) | Timer wake interval |
| `RETERMINAL_DIAGNOSTIC_HOLD_MS` | 3000 | Right-button long-press threshold |
| `RETERMINAL_DIAGNOSTIC_TIMEOUT_MS` | 600000 (10 min) | Diagnostic-mode auto-sleep |

## Pin Mapping

| Function | GPIO |
|----------|------|
| Button Left | 5 |
| Button Middle | 4 |
| Button Right | 3 |
| Buzzer | 45 |
| LED | 6 |
| EPD SCK | 7 |
| EPD MOSI | 9 |
| EPD CS | 10 |
| EPD DC | 11 |
| EPD RES | 12 |
| EPD BUSY | 13 |
| USB Serial RX | 44 |
| USB Serial TX | 43 |
| Battery ADC | 1 (2× divider; sample via `analogReadMilliVolts`) |
| Battery monitor enable | 21 (drive HIGH before sampling) |

## Dependencies

Managed automatically by PlatformIO:

- [ArduinoJson](https://arduinojson.org/) - JSON parsing
- [GxEPD2](https://github.com/ZinggJM/GxEPD2) - GPLv3 ePaper display driver

The repository's original code is MIT, but distributed firmware binaries link
GxEPD2 and require an explicit GPL compliance decision. Do not infer the
firmware binary's licensing solely from the root `LICENSE` file.

## Troubleshooting

### Device not found on USB

- Try a different USB-C cable (some are charge-only)
- Check port: `ls /dev/cu.usb*`
- The board exposes two USB-CDC bridges; only one is wired to firmware serial and esptool reset. Use `/dev/cu.usbserial-*` (CH340, `VID 1A86:7523`) for both flashing and serial monitoring. `/dev/cu.usbmodem*` (CH343, `VID 1A86:55D3`) enumerates fine but is not the firmware's `Serial1` path; esptool through that port fails with `No serial data received` because RTS/DTR cannot pulse EN.
- Hold the ESP32 module's BOOT button while connecting, or hold BOOT and tap RESET, to enter bootloader mode
- If the normal page UI is still rendering and `esptool` says `No serial data received`, the app firmware is still running and the board likely did not enter bootloader mode

### WiFi not connecting

- Check `platformio.local.ini` exists and defines `RETERMINAL_WIFI_SSID` / `RETERMINAL_WIFI_PASS`
- Ensure 2.4GHz network (ESP32 doesn't support 5GHz)
- Check serial monitor for connection status

### OTA upload fails

- Verify `upload_port` is correct in `platformio.local.ini` (`reterminal.local` should work once mDNS is visible)
- Ensure `RETERMINAL_OTA_PASSWORD` is set in `platformio.local.ini`
- Ensure device is powered and on network
- Check firewall isn't blocking port 3232. On macOS, Application Firewall can also block espota's UDP reply; briefly disable it or whitelist the Python/PlatformIO runtime if OTA reports "Host Not Found".

### Display not updating

- ePaper takes about 5-6 seconds for a visible full refresh on this panel
- Check serial monitor for errors
- Verify image is exactly 48000 bytes
- If a power cycle returns with unloaded slots, enter diagnostic mode and inspect `/status`; verify the firmware is mounting the `littlefs` partition label from `partitions-32mb.csv`, then let the next timer wake republish from the host

## Memory

- **PSRAM**: 4 pages × 48KB = 192KB stored in PSRAM
- **Heap**: ~225KB free after boot
- **Flash**: verified hardware has 32MB flash; `boards/reterminal_e1001_esp32s3.json` and `partitions-32mb.csv` allocate dual 3MB OTA apps plus ~26MB LittleFS
