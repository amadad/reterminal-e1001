# Firmware

ESP32-S3 firmware for reTerminal E1001 with HTTP API and OTA support.

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

### WiFi Credentials

Edit `src/main.cpp` and update:

```cpp
const char* WIFI_SSID = "YourNetwork";
const char* WIFI_PASS = "YourPassword";
const char* HOSTNAME = "reterminal";  // optional: change hostname
```

### OTA IP Address

Edit `platformio.ini` and set your device's IP for OTA updates:

```ini
[env:ota]
upload_port = 192.168.x.x  # Your device IP
```

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

You should see:
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

### Subsequent Updates (OTA)

Once the device is on WiFi, flash wirelessly:

```bash
# Update platformio.ini with your device IP first
pio run -e ota -t upload
```

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
- Hold BOOT button while connecting to enter bootloader mode

### WiFi not connecting

- Check credentials in `main.cpp`
- Ensure 2.4GHz network (ESP32 doesn't support 5GHz)
- Check serial monitor for connection status

### OTA upload fails

- Verify device IP is correct in `platformio.ini`
- Ensure device is powered and on network
- Check firewall isn't blocking port 3232

### Display not updating

- ePaper takes 2-3 seconds for full refresh
- Check serial monitor for errors
- Verify image is exactly 48000 bytes

## Memory

- **PSRAM**: 4 pages × 48KB = 192KB stored in PSRAM
- **Heap**: ~225KB free after boot
- **Flash**: ~1.2MB firmware size
