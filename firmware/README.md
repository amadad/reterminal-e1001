# Firmware

ESP32-S3 firmware for reTerminal E1001 with HTTP API and OTA support.

Current tracked source is designed to stay small and truthful:

- host-rendered 1-bit bitmaps
- 4 volatile slot buffers in PSRAM
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
    -DRETERMINAL_BUILD_SHA=\"unknown\"

[env:ota]
upload_port = 192.168.x.x
```

Notes:

- Wi-Fi is now configured via build flags, not hardcoded in source.
- OTA is **disabled by default** and only starts when `RETERMINAL_OTA_PASSWORD` is set.
- `platformio.local.ini` is gitignored.
- If PlatformIO reports recursive `build_flags` when using a copied local config, inline the base flags in `platformio.local.ini` instead of referencing `${env:reterminal.build_flags}`.

## Flashing

### First Time (USB)

1. Connect reTerminal to your computer via USB-C
2. Put device in bootloader mode if needed (hold BOOT while connecting)
3. Flash:

```bash
cd firmware
pio run -e reterminal -t upload
```

4. Monitor serial output:

```bash
pio device monitor
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
cd ../python
uv run reterminal discover
uv run reterminal doctor --host <device-ip>
```

### Subsequent Updates (OTA)

Once the device is on Wi-Fi, flash wirelessly:

```bash
# Set upload_port in platformio.local.ini first
pio run -e ota -t upload
```

## HTTP API

The tracked firmware source exposes:

- `GET /status`
- `GET /capabilities`
- `GET /buttons`
- `GET /beep`
- `GET/POST /page`
- `GET /snapshot`
- `POST /imageraw`
- `POST /clear`

Notes:

- `/capabilities` is the richer machine-readable contract for host software.
- `/snapshot` returns the exact stored raw bitmap for a loaded slot so host tooling can verify what the device has cached.
- `/clear` clears one slot or the full volatile cache.
- Stored pages should be treated as volatile cache, not durable persistence across power cycles, until re-probed after flashing.
- If the live device still returns `404` for `/capabilities`, `/snapshot`, or `/clear`, you are still talking to the older flashed firmware and need a reflash before expecting the newer source contract.

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

## Dependencies

Managed automatically by PlatformIO:

- [ArduinoJson](https://arduinojson.org/) - JSON parsing
- [GxEPD2](https://github.com/ZinggJM/GxEPD2) - ePaper display driver

## Troubleshooting

### Device not found on USB

- Try a different USB-C cable (some are charge-only)
- Check port: `ls /dev/cu.usb*`
- Hold the ESP32 module's BOOT button while connecting, or hold BOOT and tap RESET, to enter bootloader mode
- If the normal page UI is still rendering and `esptool` says `No serial data received`, the app firmware is still running and the board likely did not enter bootloader mode

### WiFi not connecting

- Check `platformio.local.ini` exists and defines `RETERMINAL_WIFI_SSID` / `RETERMINAL_WIFI_PASS`
- Ensure 2.4GHz network (ESP32 doesn't support 5GHz)
- Check serial monitor for connection status

### OTA upload fails

- Verify `upload_port` is correct in `platformio.local.ini`
- Ensure `RETERMINAL_OTA_PASSWORD` is set in `platformio.local.ini`
- Ensure device is powered and on network
- Check firewall isn't blocking port 3232

### Display not updating

- ePaper takes 2-3 seconds for full refresh
- Check serial monitor for errors
- Verify image is exactly 48000 bytes
- If a power cycle returns with `loaded: false`, republish from the host; the volatile cache should not yet be treated as durable across reboot

## Memory

- **PSRAM**: 4 pages × 48KB = 192KB stored in PSRAM
- **Heap**: ~225KB free after boot
- **Flash**: ~1.2MB firmware size
