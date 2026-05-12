# Firmware

ESP32-S3 firmware for reTerminal E1001 with HTTP API and OTA support.

Current tracked source is designed to stay small and truthful:

- host-rendered 1-bit bitmaps
- 4 slot buffers in PSRAM, persisted to LittleFS when storage is mounted
- buttons + HTTP control only
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

The firmware is a **deep-sleep + HTTP-pull client**, not a server. On every
wake (timer every `RETERMINAL_WAKE_INTERVAL_S`, default 1800s, or any button
via EXT1) it:

1. Connects WiFi (`WIFI_PS_MIN_MODEM`)
2. `GET <publisher>/content-hash` — JSON of per-slot SHA-256s
3. For each slot whose hash differs from the RTC-RAM fingerprint:
   `GET <publisher>/content/slot-N` → 48000 raw bytes → save to LittleFS
4. Refresh ePaper (only if anything changed)
5. `esp_deep_sleep_start()`

That's it for normal operation. The chip draws ~10 µA in deep sleep, ~100 mA
active. ~9 s awake per 1800 s cycle → ~0.5 mA average → ~60 days on a 750 mAh
cell. Matches Seeed's spec.

### Diagnostic mode

Long-press the **right** button for 3 seconds (`RETERMINAL_DIAGNOSTIC_HOLD_MS`)
while waking from EXT1. The firmware brings up:

- `GET /status` — JSON: uptime, battery_mv, RSSI, free_heap, build SHA, slot state
- `GET /eventlog` — persistent ring buffer (boot, wake_timer, wake_button, diagnostic, wifi_fail)
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
- [GxEPD2](https://github.com/ZinggJM/GxEPD2) - ePaper display driver

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
- If a power cycle returns with `loaded: false`, republish from the host and inspect LittleFS health in `/capabilities`; verify the firmware is mounting the `littlefs` partition label from `partitions-32mb.csv`

## Memory

- **PSRAM**: 4 pages × 48KB = 192KB stored in PSRAM
- **Heap**: ~225KB free after boot
- **Flash**: verified hardware has 32MB flash; `boards/reterminal_e1001_esp32s3.json` and `partitions-32mb.csv` allocate dual 3MB OTA apps plus ~26MB LittleFS
