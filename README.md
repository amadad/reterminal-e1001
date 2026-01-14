# reTerminal E1001 HTTP Firmware

Turn your Seeed reTerminal E1001 into a WiFi-controllable ePaper display.

![reTerminal E1001](https://files.seeedstudio.com/wiki/reterminal_e10xx/img/132.jpg)

## Features

- **HTTP API** - Push images, control pages, trigger buzzer via REST endpoints
- **4-Page Carousel** - Store 4 full-screen images, navigate with physical buttons
- **OTA Updates** - Flash new firmware over WiFi, no USB required after initial setup
- **Button Navigation** - Left (prev), Middle (next), Right (refresh)

## Hardware

- **Display**: 7.5" monochrome ePaper (800x480)
- **MCU**: ESP32-S3 with PSRAM
- **Buttons**: 3 tactile buttons (GPIO 3, 4, 5)
- **Buzzer**: Piezo on GPIO 45

## Quick Start

### 1. Flash the Firmware

See [firmware/README.md](firmware/README.md) for detailed flashing instructions.

```bash
cd firmware
pio run -e reterminal -t upload
```

### 2. Connect to Your Network

Edit `firmware/src/main.cpp` and set your WiFi credentials:

```cpp
const char* WIFI_SSID = "YourNetwork";
const char* WIFI_PASS = "YourPassword";
```

### 3. Find Your Device

After flashing, the display shows the IP address. Or scan your network:

```bash
arp -a | grep -i "192.168"
```

### 4. Push an Image

```bash
# Using Python client
python python/reterminal.py --host 192.168.x.x --page 0 --text "Hello World"

# Using curl (raw 800x480 1-bit bitmap)
curl -F "image=@myimage.raw" "http://192.168.x.x/imageraw?page=0"
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Device status (IP, RSSI, uptime, current page) |
| `/buttons` | GET | Button states |
| `/beep` | GET | Trigger buzzer |
| `/page` | GET | Current page info |
| `/page` | POST | Set page: `{"page": 0}` or `{"action": "next"}` |
| `/imageraw` | POST | Upload image: multipart form with `image` field, `?page=N` to store |

### Example: Push to Page

```bash
# Navigate to next page
curl -X POST -d '{"action":"next"}' http://192.168.x.x/page

# Upload image to page 0
curl -F "image=@dashboard.raw" "http://192.168.x.x/imageraw?page=0"
```

## Image Format

Images must be:
- **800x480 pixels**
- **1-bit monochrome** (black/white)
- **48,000 bytes** raw bitmap
- **MSB first**, left-to-right, top-to-bottom

Use the Python client to convert PNG/text to the correct format.

## Project Structure

```
reterminal-e1001/
├── firmware/           # PlatformIO ESP32 firmware
│   ├── src/main.cpp
│   ├── platformio.ini
│   └── README.md
├── python/             # Python client library
│   ├── reterminal.py
│   └── examples/
└── README.md
```

## Credits

Hardware reference from [Handy4ndy/Handy-reTerminal-E1001](https://github.com/Handy4ndy/Handy-reTerminal-E1001)

## License

MIT
