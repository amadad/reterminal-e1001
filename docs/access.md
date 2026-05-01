# Accessing the reTerminal from coding agents

Public-safe operational notes for Claude Code, pi, and other headless coding agents working from this repo.

## Mental model

There are two separate access paths:

1. **HTTP over Wi-Fi** — the device control plane.
   - Used for `status`, `capabilities`, `snapshot`, `clear`, slot upload, and page selection.
   - Driven by the Python CLI in `./python`.
2. **USB serial** — diagnostics and firmware maintenance.
   - Used for boot logs, bootloader interrogation, serial monitor, and PlatformIO flashing.
   - It is **not** a slot upload/status API. If Wi-Fi discovery fails, USB can prove the device is alive, but slot operations still require HTTP reachability.

## Repository paths

From repo root (`reterminal-e1001/`):

| Area | Path | Tooling |
|---|---|---|
| Python control plane | `python/` | `uv run reterminal ...` |
| Python package import root | `python/reterminal/` | import as `reterminal` when `python/` is the project root |
| Firmware | `firmware/` | `pio run ...` / `pio device monitor ...` |
| Firmware local config | `firmware/platformio.local.ini` | gitignored; may contain local Wi-Fi/OTA values |
| Local feed override | `python/examples/kitchen-display.local.json` | gitignored; keep private content paths here |
| Launchd template | `scripts/sh.reterminal.publish.example.plist` | public template; copy/edit outside git for local use |

Do **not** run `uv run reterminal ...` from repo root without telling `uv` where the Python project lives. Either `cd python` first or use `uv --directory python`.

## Python / uv commands

Preferred from repo root:

```bash
env -u VIRTUAL_ENV uv --directory python run reterminal config --output json
env -u VIRTUAL_ENV uv --directory python run reterminal discover --output json
env -u VIRTUAL_ENV uv --directory python run reterminal doctor --output json
```

Preferred from `python/`:

```bash
env -u VIRTUAL_ENV uv run reterminal config --output json
env -u VIRTUAL_ENV uv run reterminal discover --output json
env -u VIRTUAL_ENV uv run reterminal doctor --output json
```

If you see a warning like:

```text
VIRTUAL_ENV=... does not match the project environment path `.venv` and will be ignored
```

it means the shell inherited an unrelated virtualenv. It is usually harmless, but prefixing commands with `env -u VIRTUAL_ENV` avoids the warning and prevents agents from chasing the wrong Python path.

Discovery JSON is a list of reachable targets. To export the first discovered host:

```bash
export RETERMINAL_HOST=$(
  env -u VIRTUAL_ENV uv --directory python run reterminal discover --output json \
    | jq -r '.[0].target // empty'
)
```

If this is empty, do not guess an old DHCP lease. Use USB serial logs to diagnose Wi-Fi, then rediscover.

## HTTP device access

Once a host is known:

```bash
env -u VIRTUAL_ENV uv --directory python run reterminal doctor --host "$RETERMINAL_HOST"
env -u VIRTUAL_ENV uv --directory python run reterminal status --host "$RETERMINAL_HOST" --output json
env -u VIRTUAL_ENV uv --directory python run reterminal capabilities --host "$RETERMINAL_HOST" --output json
env -u VIRTUAL_ENV uv --directory python run reterminal snapshot --host "$RETERMINAL_HOST" --png /tmp/reterminal-current.png --output json
```

On some macOS networks, Python `requests` can report `No route to host` while
`curl` works against the same device. The CLI falls back to `curl` for device
HTTP operations and discovery probes, so prefer the CLI/curl path over ad hoc
Python `requests` snippets when debugging live hardware.

For live mutations, follow the repo safety rule: preview first, then use `--live` only after explicit approval.

## USB serial access on macOS

Use callout devices (`/dev/cu.*`) for connecting from tools. The matching `/dev/tty.*` devices may also exist, but `/dev/cu.*` is the normal macOS path for PlatformIO/serial monitor.

Discover current USB serial devices:

```bash
pio device list
ls -l /dev/cu.usb* /dev/tty.usb* 2>/dev/null || true
lsof /dev/cu.usbserial-* /dev/cu.usbmodem* 2>/dev/null || true
```

Common ESP32 USB-serial devices appear as `/dev/cu.usbserial-*` or `/dev/cu.usbmodem*`. The suffix changes with cable, hub, and boot mode. Do not hardcode a serial path in docs or scripts; re-run `pio device list` each session.

If a port is busy, `lsof` will show the owning process. Stop only monitors/loggers that you started; do not kill unrelated user processes blindly.

## Serial monitor

From `firmware/`:

```bash
pio device monitor -p /dev/cu.usbserial-XXXX -b 115200
```

Replace the port with the current value from `pio device list`. Useful boot-log lines include:

```text
Connecting to WiFi...
Connected! IP: 192.168.x.x
HTTP server started
OTA ready
Full refresh page N (slot-N)
```

If serial logs show page refreshes but `reterminal discover` returns `[]`, the device is alive over USB but not reachable over Wi-Fi/HTTP from the host.

## Firmware build and USB flash

Firmware uses PlatformIO, not `uv`.

```bash
cd firmware
pio run -e reterminal
pio run -e reterminal -t upload --upload-port /dev/cu.usbserial-XXXX
```

If the current uploadable device is a `/dev/cu.usbmodem*` path instead, use that path in `--upload-port`. If upload cannot enter the bootloader, hold BOOT while connecting or hold BOOT and tap RESET, then retry.

After flashing, monitor serial until Wi-Fi starts, then return to the Python control plane:

```bash
cd ..
env -u VIRTUAL_ENV uv --directory python run reterminal discover
env -u VIRTUAL_ENV uv --directory python run reterminal doctor --host <device-ip>
```

## Common agent mistakes

- Treating USB serial as if it exposes the HTTP slot API. It does not.
- Running `uv run` from repo root and then debugging the wrong Python environment. Use `uv --directory python` or `cd python`.
- Setting `PYTHONPATH=python/reterminal`; the package root is the parent directory `python/`, not the package directory itself.
- Using stale DHCP addresses from older notes. Always discover or read the boot log IP.
- Pasting `firmware/platformio.local.ini` output into logs. It can contain local network/OTA configuration.
- Reintroducing old fixed-page `refresh`/`watch` commands. Use `reterminal publish` with provider manifests.
