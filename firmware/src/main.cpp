/*
 * reTerminal E1001 HTTP API Firmware
 * Based on Handy4ndy's working GxEPD2 examples
 *
 * Endpoints:
 *   GET  /status        - Device status + health fields
 *   GET  /capabilities  - Firmware-reported device contract
 *   GET  /buttons       - Button states
 *   GET  /beep          - Test buzzer
 *   GET/POST /page      - Get/set current page
 *   GET  /snapshot      - Read back a stored raw bitmap (800x480, 48000 bytes)
 *   POST /imageraw      - Upload raw 1-bit image (800x480, 48000 bytes)
 *   POST /clear         - Clear one slot or the stored slot cache
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <ArduinoOTA.h>
#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <GxEPD2_BW.h>
#include <Fonts/FreeMonoBold18pt7b.h>
#include <LittleFS.h>
#include <esp_system.h>
#include <esp_task_wdt.h>
#include <esp_sleep.h>
#include <driver/rtc_io.h>
#include <stdlib.h>

#ifndef RETERMINAL_WIFI_SSID
#define RETERMINAL_WIFI_SSID ""
#endif

#ifndef RETERMINAL_WIFI_PASS
#define RETERMINAL_WIFI_PASS ""
#endif

#ifndef RETERMINAL_HOSTNAME
#define RETERMINAL_HOSTNAME "reterminal"
#endif

#ifndef RETERMINAL_OTA_PASSWORD
#define RETERMINAL_OTA_PASSWORD ""
#endif

#ifndef RETERMINAL_FIRMWARE_VERSION
#define RETERMINAL_FIRMWARE_VERSION "dev"
#endif

#ifndef RETERMINAL_BUILD_SHA
#define RETERMINAL_BUILD_SHA "unknown"
#endif

// Legacy diagnostic-mode safety nets. The device deep-sleeps in normal
// operation, so these only fire if you've put it in diagnostic mode and
// left it there. They're preserved unchanged from the always-on firmware.
#ifndef RETERMINAL_WIFI_SELF_RESTART_MS
#define RETERMINAL_WIFI_SELF_RESTART_MS 600000UL
#endif
#ifndef RETERMINAL_PERIODIC_RESTART_MS
#define RETERMINAL_PERIODIC_RESTART_MS 43200000UL  // 12 hours
#endif
#ifndef RETERMINAL_HTTP_IDLE_RESTART_MS
#define RETERMINAL_HTTP_IDLE_RESTART_MS 1800000UL  // 30 min
#endif

// Battery-mode wake interval. The device deep-sleeps between cycles, wakes
// briefly to poll the publisher for content changes, and sleeps again. At
// 30min cycles with ~5s awake per cycle, average current is well under 1 mA
// and a 750 mAh cell lasts months.
#ifndef RETERMINAL_WAKE_INTERVAL_S
#define RETERMINAL_WAKE_INTERVAL_S 1800UL
#endif

// Long-press of the right button at boot (i.e., held through wake from EXT1)
// enters diagnostic mode: full HTTP server + mDNS + OTA come up for this many
// ms, then the device returns to deep sleep.
#ifndef RETERMINAL_DIAGNOSTIC_HOLD_MS
#define RETERMINAL_DIAGNOSTIC_HOLD_MS 3000UL
#endif

#ifndef RETERMINAL_DIAGNOSTIC_TIMEOUT_MS
#define RETERMINAL_DIAGNOSTIC_TIMEOUT_MS 600000UL  // 10 minutes
#endif

// host:port where the publisher serves /content-hash and /content/slot-N.
// Empty disables the pull path (cold boot will still restore from flash).
#ifndef RETERMINAL_PUBLISHER_HOST
#define RETERMINAL_PUBLISHER_HOST ""
#endif

#ifndef RETERMINAL_PUBLISHER_PORT
#define RETERMINAL_PUBLISHER_PORT 8765
#endif

const char* WIFI_SSID = RETERMINAL_WIFI_SSID;
const char* WIFI_PASS = RETERMINAL_WIFI_PASS;
const char* HOSTNAME = RETERMINAL_HOSTNAME;
const char* OTA_PASSWORD = RETERMINAL_OTA_PASSWORD;
const char* FIRMWARE_VERSION = RETERMINAL_FIRMWARE_VERSION;
const char* BUILD_SHA = RETERMINAL_BUILD_SHA;
const char* BUILD_TIME = __DATE__ " " __TIME__;

// Display pins (SPI)
#define EPD_SCK_PIN 7
#define EPD_MOSI_PIN 9
#define EPD_CS_PIN 10
#define EPD_DC_PIN 11
#define EPD_RES_PIN 12
#define EPD_BUSY_PIN 13

// Button pins
#define BTN_LEFT 5    // Left button - GPIO5
#define BTN_MIDDLE 4  // Middle button - GPIO4
#define BTN_RIGHT 3   // Right/Green button - GPIO3
#define BUZZER_PIN 45
#define LED_PIN 6

// Display dimensions
#define DISPLAY_WIDTH 800
#define DISPLAY_HEIGHT 480
#define IMAGE_BYTES (DISPLAY_WIDTH * DISPLAY_HEIGHT / 8)  // 48000 bytes

// Page system
int currentPage = 0;
const int NUM_PAGES = 4;
const char* PAGE_NAMES[] = {"slot-0", "slot-1", "slot-2", "slot-3"};
uint8_t* pageStorage[NUM_PAGES] = {nullptr};
bool pageLoaded[NUM_PAGES] = {false};

// Flash persistence
bool fsReady = false;
const char* SLOT_DIR = "/slots";
const char* STATE_FILE = "/state.json";

// Button state tracking
bool lastLeft = HIGH, lastMiddle = HIGH, lastRight = HIGH;
unsigned long lastButtonPress = 0;
const unsigned long DEBOUNCE_MS = 50;

unsigned long lastWifiOkMs = 0;
unsigned long lastWifiLostMs = 0;
unsigned long wifiReconnectAttempts = 0;
unsigned long lastWifiReconnectMs = 0;
bool mdnsReady = false;
bool otaReady = false;
const unsigned long WIFI_SELF_RESTART_MS = RETERMINAL_WIFI_SELF_RESTART_MS;
const unsigned long PERIODIC_RESTART_MS = RETERMINAL_PERIODIC_RESTART_MS;
const unsigned long HTTP_IDLE_RESTART_MS = RETERMINAL_HTTP_IDLE_RESTART_MS;

// ARP keepalive removed. It was added on the zombie-WiFi hypothesis that the
// eventlog data later disproved (true failure mode is brownout cascade during
// battery depletion). Deep sleep eliminates the always-on regime that the
// theory required, so it no longer earns its keep.

// HTTP-client liveness, used by the idle restart check. Updated at the top of
// every HTTP handler — proves something on the LAN actually reached our TCP
// stack and got a response back.
volatile unsigned long lastClientMs = 0;
volatile unsigned long httpRequestCount = 0;

// Loop-task watchdog: reboots the device if loop() stops iterating for this
// long. Catches synchronous WebServer wedges on half-open TCP, SPI hangs, and
// any other path that blocks the main task. The previous `delay(1)` in paint
// loops only fed the IDLE task watchdog; nothing armed a watchdog on loopTask
// itself, so an indefinitely-blocked loop never recovered.
const uint32_t LOOP_WDT_TIMEOUT_S = 60;
bool loopWatchdogArmed = false;
esp_err_t loopWatchdogInitStatus = ESP_OK;
esp_err_t loopWatchdogAddStatus = ESP_OK;

enum SelfRestartReason : uint32_t {
  SELF_RESTART_NONE = 0,
  SELF_RESTART_WIFI_STALE = 1,
  SELF_RESTART_PERIODIC = 2,
  SELF_RESTART_HTTP_IDLE = 3,
};

RTC_DATA_ATTR uint32_t selfRestartCount = 0;
RTC_DATA_ATTR uint32_t lastSelfRestartReasonCode = SELF_RESTART_NONE;
RTC_DATA_ATTR uint32_t lastSelfRestartUptimeMs = 0;

// State that must survive deep-sleep but not poweron. RTC RAM is cleared on
// true poweron / brownout; we use a magic check to detect first boot.
const uint32_t RTC_STATE_MAGIC = 0x52455445;  // 'RETE'
RTC_DATA_ATTR uint32_t rtcStateMagic = 0;
RTC_DATA_ATTR uint32_t bootCount = 0;
RTC_DATA_ATTR uint32_t slotHashFingerprint[NUM_PAGES] = {0};
RTC_DATA_ATTR int rtcVisibleSlot = 0;

// Diagnostic mode: full HTTP server + mDNS + OTA, like the original always-on
// firmware. Entered by long-pressing right button while waking from EXT1.
// Exits to deep sleep after RETERMINAL_DIAGNOSTIC_TIMEOUT_MS.
bool diagnosticMode = false;
unsigned long diagnosticEntryMs = 0;

// === Persistent event log ===
// Ring buffer in LittleFS for freeze post-mortems. Entries are 24 bytes so
// a heartbeat can carry battery_mv + rssi + heap snapshots, not just a
// timestamp + event code. Magic bumped from RELG when entry size grew, so
// older format files (16-byte entries) are rejected cleanly on first load.
enum EventCode : uint8_t {
  EVENT_NONE = 0,
  EVENT_BOOT = 1,
  EVENT_WIFI_LOST = 2,
  EVENT_WIFI_RESTORED = 3,
  EVENT_RESTART_PERIODIC = 4,
  EVENT_RESTART_WIFI_STALE = 5,
  EVENT_RESTART_HTTP_IDLE = 6,
  EVENT_HEARTBEAT = 7,
};

struct EventLogEntry {
  uint32_t ts_ms;
  uint8_t  event_code;
  uint8_t  reset_reason_code;  // ESP reset reason, meaningful on boot events
  uint16_t restart_count;       // selfRestartCount snapshot
  uint32_t extra1;
  uint32_t extra2;
  uint16_t battery_mv;
  int16_t  rssi_dbm;
  uint16_t free_heap_kb;
  uint16_t reserved;
};  // 24 bytes

const int EVENT_LOG_CAPACITY = 64;  // ~5h history at 5min heartbeat interval
const char* EVENT_LOG_PATH = "/eventlog.bin";
const uint32_t EVENT_LOG_MAGIC = 0x52454C48;  // 'RELH' (entry size bumped from RELG)

struct EventLogHeader {
  uint32_t magic;
  uint32_t write_index;
  uint32_t total_appended;
  uint32_t reserved;
};  // 16 bytes

EventLogHeader eventLogHeader = {EVENT_LOG_MAGIC, 0, 0, 0};
EventLogEntry eventLogBuffer[EVENT_LOG_CAPACITY] = {};

// reTerminal E1001 reads battery voltage on GPIO1 through a 2x divider
// (two 10kohm resistors); the divider is gated by GPIO21 which must be
// driven HIGH to feed the ADC. Without that, GPIO1 reads 0. ADC needs
// ADC_11db attenuation to cover the ~2.1V max divider output.
const int BATTERY_ADC_PIN = 1;
const int BATTERY_ENABLE_PIN = 21;
const float BATTERY_DIVIDER = 2.0f;
const unsigned long HEARTBEAT_INTERVAL_MS = 300000UL;  // 5 minutes
unsigned long lastHeartbeatMs = 0;

uint16_t readBatteryMv() {
  uint32_t raw = analogReadMilliVolts(BATTERY_ADC_PIN);
  return static_cast<uint16_t>(raw * BATTERY_DIVIDER);
}

GxEPD2_BW<GxEPD2_750_GDEY075T7, GxEPD2_750_GDEY075T7::HEIGHT> display(
    GxEPD2_750_GDEY075T7(EPD_CS_PIN, EPD_DC_PIN, EPD_RES_PIN, EPD_BUSY_PIN));
SPIClass hspi(HSPI);

WebServer server(80);

uint8_t* imageBuffer = nullptr;

HardwareSerial &usbSerial = Serial1;

void beep(int duration_ms = 300) {
  tone(BUZZER_PIN, 1000, duration_ms);
}

void printCentered(const char* text, int y) {
  int16_t x1, y1;
  uint16_t w, h;
  display.getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
  int x = (DISPLAY_WIDTH - w) / 2;
  display.setCursor(x, y);
  display.print(text);
}

// === Flash persistence ===

String slotPath(int page) {
  return String(SLOT_DIR) + "/slot-" + String(page) + ".raw";
}

void saveSlotToFlash(int page) {
  if (!fsReady || !pageLoaded[page] || pageStorage[page] == nullptr) return;
  File f = LittleFS.open(slotPath(page), "w");
  if (!f) return;
  f.write(pageStorage[page], IMAGE_BYTES);
  f.close();
  usbSerial.printf("Saved slot %d to flash\n", page);
}

bool loadSlotFromFlash(int page) {
  if (!fsReady || pageStorage[page] == nullptr) return false;
  File f = LittleFS.open(slotPath(page), "r");
  if (!f || f.size() != IMAGE_BYTES) {
    if (f) f.close();
    return false;
  }
  f.read(pageStorage[page], IMAGE_BYTES);
  f.close();
  pageLoaded[page] = true;
  usbSerial.printf("Loaded slot %d from flash\n", page);
  return true;
}

void removeSlotFromFlash(int page) {
  if (!fsReady) return;
  LittleFS.remove(slotPath(page));
}

void saveState() {
  if (!fsReady) return;
  File f = LittleFS.open(STATE_FILE, "w");
  if (!f) return;
  JsonDocument doc;
  doc["currentPage"] = currentPage;
  serializeJson(doc, f);
  f.close();
}

int loadState() {
  if (!fsReady) return 0;
  File f = LittleFS.open(STATE_FILE, "r");
  if (!f) return 0;
  JsonDocument doc;
  if (deserializeJson(doc, f) != DeserializationError::Ok) {
    f.close();
    return 0;
  }
  f.close();
  int page = doc["currentPage"] | 0;
  if (page < 0 || page >= NUM_PAGES) return 0;
  return page;
}

// === Display rendering ===

// Full refresh on every path: this panel's partial-update LUT can't handle the
// large pixel deltas of a full-frame slot swap without leaving ghosted artifacts.
void showPage(int page) {
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    if (pageLoaded[page] && pageStorage[page] != nullptr) {
      display.drawBitmap(0, 0, pageStorage[page], DISPLAY_WIDTH, DISPLAY_HEIGHT, GxEPD_BLACK);
    } else {
      display.setFont(&FreeMonoBold18pt7b);
      display.setTextColor(GxEPD_BLACK);
      String title = String(PAGE_NAMES[page]);
      title.toUpperCase();
      printCentered(title.c_str(), 200);
      printCentered("No image loaded", 260);
    }
    delay(1);
  } while (display.nextPage());
  display.hibernate();
  usbSerial.printf("Full refresh page %d (%s)\n", page, PAGE_NAMES[page]);
}

void showBootScreen() {
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    display.setFont(&FreeMonoBold18pt7b);
    display.setTextColor(GxEPD_BLACK);
    printCentered("reTerminal E1001", 180);
    printCentered("Connecting to WiFi...", 240);
    delay(1);
  } while (display.nextPage());
  display.hibernate();
}

void showReadyScreen(String ip) {
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    display.setFont(&FreeMonoBold18pt7b);
    display.setTextColor(GxEPD_BLACK);
    printCentered("reTerminal E1001", 160);
    printCentered("Ready!", 220);
    String ipLine = "IP: " + ip;
    printCentered(ipLine.c_str(), 280);
    printCentered("Press buttons to navigate", 340);
    delay(1);
  } while (display.nextPage());
  display.hibernate();
}

void showConfigRequiredScreen(const char* title, const char* detail) {
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    display.setFont(&FreeMonoBold18pt7b);
    display.setTextColor(GxEPD_BLACK);
    printCentered("reTerminal E1001", 140);
    printCentered(title, 220);
    printCentered(detail, 300);
    delay(1);
  } while (display.nextPage());
  display.hibernate();
}

bool isValidPageIndex(int page) {
  return page >= 0 && page < NUM_PAGES;
}

bool parseIntegerStrict(const String& raw, int* value) {
  if (raw.length() == 0 || value == nullptr) {
    return false;
  }

  char* end = nullptr;
  long parsed = strtol(raw.c_str(), &end, 10);
  if (end == raw.c_str() || *end != '\0') {
    return false;
  }

  *value = static_cast<int>(parsed);
  return true;
}

void showBlankScreen() {
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    delay(1);
  } while (display.nextPage());
  display.hibernate();
}

void clearStoredPage(int page) {
  if (!isValidPageIndex(page)) {
    return;
  }
  if (pageStorage[page] != nullptr) {
    memset(pageStorage[page], 0xFF, IMAGE_BYTES);
  }
  pageLoaded[page] = false;
  removeSlotFromFlash(page);
}

const char* resetReasonName(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON: return "poweron";
    case ESP_RST_EXT: return "external";
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT: return "interrupt_watchdog";
    case ESP_RST_TASK_WDT: return "task_watchdog";
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_DEEPSLEEP: return "deepsleep";
    case ESP_RST_BROWNOUT: return "brownout";
    case ESP_RST_SDIO: return "sdio";
    default: return "unknown";
  }
}

const char* selfRestartReasonName(uint32_t reason) {
  switch (reason) {
    case SELF_RESTART_NONE: return "none";
    case SELF_RESTART_WIFI_STALE: return "wifi_stale";
    case SELF_RESTART_PERIODIC: return "periodic";
    case SELF_RESTART_HTTP_IDLE: return "http_idle";
    default: return "unknown";
  }
}

const char* eventCodeName(uint8_t code) {
  switch (code) {
    case EVENT_NONE: return "none";
    case EVENT_BOOT: return "boot";
    case EVENT_WIFI_LOST: return "wifi_lost";
    case EVENT_WIFI_RESTORED: return "wifi_restored";
    case EVENT_RESTART_PERIODIC: return "restart_periodic";
    case EVENT_RESTART_WIFI_STALE: return "restart_wifi_stale";
    case EVENT_RESTART_HTTP_IDLE: return "restart_http_idle";
    case EVENT_HEARTBEAT: return "heartbeat";
    default: return "unknown";
  }
}

void markClientActivity() {
  lastClientMs = millis();
  httpRequestCount++;
}

// === Event log persistence ===

void eventLogLoad() {
  if (!fsReady) return;
  File f = LittleFS.open(EVENT_LOG_PATH, "r");
  if (!f) return;
  size_t expected = sizeof(eventLogHeader) + sizeof(eventLogBuffer);
  if (f.size() != expected) {
    f.close();
    return;
  }
  EventLogHeader hdr;
  if (f.read(reinterpret_cast<uint8_t*>(&hdr), sizeof(hdr)) != sizeof(hdr)
      || hdr.magic != EVENT_LOG_MAGIC) {
    f.close();
    return;
  }
  if (f.read(reinterpret_cast<uint8_t*>(eventLogBuffer), sizeof(eventLogBuffer))
      != sizeof(eventLogBuffer)) {
    f.close();
    return;
  }
  f.close();
  eventLogHeader = hdr;
  if (eventLogHeader.write_index >= EVENT_LOG_CAPACITY) {
    eventLogHeader.write_index = 0;
  }
}

void eventLogPersist() {
  if (!fsReady) return;
  File f = LittleFS.open(EVENT_LOG_PATH, "w");
  if (!f) return;
  f.write(reinterpret_cast<const uint8_t*>(&eventLogHeader), sizeof(eventLogHeader));
  f.write(reinterpret_cast<const uint8_t*>(eventLogBuffer), sizeof(eventLogBuffer));
  f.close();
}

void eventLogAppend(uint8_t code, uint32_t extra1 = 0, uint32_t extra2 = 0) {
  EventLogEntry& slot = eventLogBuffer[eventLogHeader.write_index];
  slot.ts_ms = millis();
  slot.event_code = code;
  slot.reset_reason_code = static_cast<uint8_t>(esp_reset_reason());
  slot.restart_count = static_cast<uint16_t>(selfRestartCount);
  slot.extra1 = extra1;
  slot.extra2 = extra2;
  slot.battery_mv = readBatteryMv();
  slot.rssi_dbm = WiFi.RSSI();
  slot.free_heap_kb = static_cast<uint16_t>(ESP.getFreeHeap() / 1024);
  slot.reserved = 0;
  eventLogHeader.write_index = (eventLogHeader.write_index + 1) % EVENT_LOG_CAPACITY;
  eventLogHeader.total_appended++;
  eventLogPersist();
}

bool wifiLinkUp() {
  return WiFi.status() == WL_CONNECTED && WiFi.localIP() != IPAddress(0, 0, 0, 0);
}

unsigned long wifiDownDurationMs(unsigned long now) {
  if (lastWifiLostMs == 0) return 0;
  return now - lastWifiLostMs;
}

void appendCapabilityFields(JsonDocument& doc) {
  unsigned long now = millis();
  doc["hostname"] = HOSTNAME;
  doc["firmware_version"] = FIRMWARE_VERSION;
  doc["build_sha"] = BUILD_SHA;
  doc["build_time"] = BUILD_TIME;
  doc["width"] = DISPLAY_WIDTH;
  doc["height"] = DISPLAY_HEIGHT;
  doc["image_bytes"] = IMAGE_BYTES;
  doc["page_slots"] = NUM_PAGES;
  doc["snapshot_readback"] = true;
  doc["persistent_storage"] = fsReady;
  doc["current_page"] = currentPage;
  doc["current_page_name"] = PAGE_NAMES[currentPage];
  doc["current_page_loaded"] = pageLoaded[currentPage];
  doc["reset_reason"] = resetReasonName(esp_reset_reason());
  doc["wifi_connected"] = wifiLinkUp();
  doc["wifi_status"] = WiFi.status();
  doc["wifi_reconnect_attempts"] = wifiReconnectAttempts;
  doc["last_wifi_ok_ms"] = lastWifiOkMs;
  doc["last_wifi_lost_ms"] = lastWifiLostMs;
  doc["last_wifi_reconnect_ms"] = lastWifiReconnectMs;
  doc["wifi_down_ms"] = wifiDownDurationMs(now);
  doc["wifi_self_restart_ms"] = WIFI_SELF_RESTART_MS;
  doc["periodic_restart_ms"] = PERIODIC_RESTART_MS;
  doc["http_idle_restart_ms"] = HTTP_IDLE_RESTART_MS;
  doc["last_client_ms"] = lastClientMs;
  doc["http_idle_ms"] = (lastClientMs == 0) ? 0UL : (now - lastClientMs);
  doc["http_request_count"] = httpRequestCount;
  doc["event_log_total"] = eventLogHeader.total_appended;
  doc["event_log_capacity"] = EVENT_LOG_CAPACITY;
  doc["battery_mv"] = readBatteryMv();
  doc["heartbeat_interval_ms"] = HEARTBEAT_INTERVAL_MS;
  doc["self_restart_count"] = selfRestartCount;
  doc["last_self_restart_reason"] = selfRestartReasonName(lastSelfRestartReasonCode);
  doc["last_self_restart_uptime_ms"] = lastSelfRestartUptimeMs;
  doc["mdns_ready"] = mdnsReady;
  doc["ota_ready"] = otaReady;
  doc["loop_watchdog_armed"] = loopWatchdogArmed;
  doc["loop_watchdog_timeout_s"] = LOOP_WDT_TIMEOUT_S;
  doc["loop_watchdog_init_status"] = static_cast<int>(loopWatchdogInitStatus);
  doc["loop_watchdog_add_status"] = static_cast<int>(loopWatchdogAddStatus);
  doc["free_psram"] = ESP.getFreePsram();
  doc["min_free_heap"] = ESP.getMinFreeHeap();
  if (fsReady) {
    doc["littlefs_total_bytes"] = LittleFS.totalBytes();
    doc["littlefs_used_bytes"] = LittleFS.usedBytes();
  }

  JsonArray loadedPages = doc["loaded_pages"].to<JsonArray>();
  JsonArray slotNames = doc["slot_names"].to<JsonArray>();
  for (int i = 0; i < NUM_PAGES; i++) {
    loadedPages.add(pageLoaded[i]);
    slotNames.add(PAGE_NAMES[i]);
  }
}

void sendJsonError(int status, const String& message) {
  server.send(status, "application/json", "{\"error\": \"" + message + "\"}");
}

// === HTTP Handlers ===

void handleRoot() {
  markClientActivity();
  String html = "<h1>reTerminal E1001</h1>";
  html += "<p>IP: " + WiFi.localIP().toString() + "</p>";
  html += "<p>Endpoints: /status, /capabilities, /buttons, /beep, /page, /snapshot, /imageraw, /clear</p>";
  server.send(200, "text/html", html);
}

void handleStatus() {
  markClientActivity();
  JsonDocument doc;
  doc["ip"] = WiFi.localIP().toString();
  doc["rssi"] = WiFi.RSSI();
  doc["ssid"] = WiFi.SSID();
  doc["uptime_ms"] = millis();
  doc["free_heap"] = ESP.getFreeHeap();
  appendCapabilityFields(doc);

  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void handleCapabilities() {
  markClientActivity();
  JsonDocument doc;
  doc["ip"] = WiFi.localIP().toString();
  doc["ssid"] = WiFi.SSID();
  doc["rssi"] = WiFi.RSSI();
  doc["uptime_ms"] = millis();
  doc["free_heap"] = ESP.getFreeHeap();
  appendCapabilityFields(doc);

  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void handleSnapshot() {
  markClientActivity();
  if (server.method() != HTTP_GET) {
    sendJsonError(405, "Method Not Allowed");
    return;
  }

  int targetPage = currentPage;
  String pageArg = server.arg("page");
  if (pageArg.length() > 0) {
    if (!parseIntegerStrict(pageArg, &targetPage) || !isValidPageIndex(targetPage)) {
      sendJsonError(400, "Page out of range");
      return;
    }
  }

  if (!pageLoaded[targetPage] || pageStorage[targetPage] == nullptr) {
    server.send(404, "application/json",
      "{\"error\": \"No stored bitmap\", \"page\": " + String(targetPage) + ", \"loaded\": false}");
    return;
  }

  server.sendHeader("Cache-Control", "no-store");
  server.sendHeader("X-reTerminal-Page", String(targetPage));
  server.sendHeader("X-reTerminal-Name", PAGE_NAMES[targetPage]);
  server.sendHeader("X-reTerminal-Width", String(DISPLAY_WIDTH));
  server.sendHeader("X-reTerminal-Height", String(DISPLAY_HEIGHT));
  server.sendHeader("X-reTerminal-Image-Bytes", String(IMAGE_BYTES));
  server.setContentLength(IMAGE_BYTES);
  server.send(200, "application/octet-stream", "");
  server.client().write(pageStorage[targetPage], IMAGE_BYTES);
}

void handleButtons() {
  markClientActivity();
  JsonDocument doc;
  doc["btn_left"] = digitalRead(BTN_LEFT);
  doc["btn_middle"] = digitalRead(BTN_MIDDLE);
  doc["btn_right"] = digitalRead(BTN_RIGHT);
  doc["left_gpio"] = BTN_LEFT;
  doc["middle_gpio"] = BTN_MIDDLE;
  doc["right_gpio"] = BTN_RIGHT;

  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void handleBeep() {
  markClientActivity();
  beep(300);
  server.send(200, "application/json", "{\"beeped\": true}");
}

void handlePage() {
  markClientActivity();
  if (server.method() == HTTP_GET) {
    JsonDocument doc;
    doc["page"] = currentPage;
    doc["name"] = PAGE_NAMES[currentPage];
    doc["total"] = NUM_PAGES;
    doc["loaded"] = pageLoaded[currentPage];
    String response;
    serializeJson(doc, response);
    server.send(200, "application/json", response);
    return;
  }

  if (server.method() != HTTP_POST) {
    sendJsonError(405, "Method Not Allowed");
    return;
  }

  String body = server.arg("plain");
  JsonDocument doc;
  if (deserializeJson(doc, body) != DeserializationError::Ok) {
    sendJsonError(400, "Invalid JSON");
    return;
  }

  if (doc["page"].is<int>()) {
    int requestedPage = doc["page"].as<int>();
    if (!isValidPageIndex(requestedPage)) {
      sendJsonError(400, "Page out of range");
      return;
    }
    currentPage = requestedPage;
  } else if (doc["action"].is<const char*>()) {
    const char* action = doc["action"];
    if (strcmp(action, "next") == 0) {
      currentPage = (currentPage + 1) % NUM_PAGES;
    } else if (strcmp(action, "prev") == 0) {
      currentPage = (currentPage - 1 + NUM_PAGES) % NUM_PAGES;
    } else {
      sendJsonError(400, "Unsupported action");
      return;
    }
  } else {
    sendJsonError(400, "Expected 'page' or 'action'");
    return;
  }

  showPage(currentPage);
  saveState();

  JsonDocument resp;
  resp["page"] = currentPage;
  resp["name"] = PAGE_NAMES[currentPage];
  String response;
  serializeJson(resp, response);
  server.send(200, "application/json", response);
}

// Upload state for chunked image uploads
size_t uploadBytesReceived = 0;
int uploadTargetPage = -1;
bool uploadTargetSpecified = false;
bool uploadTargetInvalid = false;

void resetUploadState() {
  uploadBytesReceived = 0;
  uploadTargetPage = -1;
  uploadTargetSpecified = false;
  uploadTargetInvalid = false;
}

void handleImageUpload() {
  HTTPUpload& upload = server.upload();

  if (upload.status == UPLOAD_FILE_START) {
    markClientActivity();
    resetUploadState();

    String pageArg = server.arg("page");
    if (pageArg.length() > 0) {
      uploadTargetSpecified = true;
      int requestedPage = -1;
      if (parseIntegerStrict(pageArg, &requestedPage) && isValidPageIndex(requestedPage)) {
        uploadTargetPage = requestedPage;
      } else {
        uploadTargetInvalid = true;
      }
    }

    if (imageBuffer == nullptr) {
      imageBuffer = (uint8_t*)ps_malloc(IMAGE_BYTES);
      if (imageBuffer == nullptr) imageBuffer = (uint8_t*)malloc(IMAGE_BYTES);
    }

    usbSerial.printf("Upload started, target page %d\n", uploadTargetPage);

  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (imageBuffer != nullptr && uploadBytesReceived + upload.currentSize <= IMAGE_BYTES) {
      memcpy(imageBuffer + uploadBytesReceived, upload.buf, upload.currentSize);
      uploadBytesReceived += upload.currentSize;
    }

  } else if (upload.status == UPLOAD_FILE_END) {
    usbSerial.printf("Upload complete: %d bytes\n", uploadBytesReceived);
  }
}

void handleImageRaw() {
  markClientActivity();
  if (server.method() != HTTP_POST) {
    sendJsonError(405, "Method Not Allowed");
    return;
  }

  if (uploadTargetInvalid) {
    resetUploadState();
    sendJsonError(400, "Page out of range");
    return;
  }

  if (uploadBytesReceived != IMAGE_BYTES) {
    server.send(400, "application/json",
      "{\"error\": \"Invalid size\", \"expected\": " + String(IMAGE_BYTES) +
      ", \"received\": " + String(uploadBytesReceived) + "}");
    resetUploadState();
    return;
  }

  if (imageBuffer == nullptr) {
    resetUploadState();
    sendJsonError(500, "No buffer");
    return;
  }

  if (uploadTargetSpecified) {
    if (pageStorage[uploadTargetPage] == nullptr) {
      resetUploadState();
      sendJsonError(500, "Target page storage unavailable");
      return;
    }

    bool unchanged = pageLoaded[uploadTargetPage]
      && memcmp(pageStorage[uploadTargetPage], imageBuffer, IMAGE_BYTES) == 0;
    if (unchanged) {
      server.send(200, "application/json",
        "{\"success\": true, \"page\": " + String(uploadTargetPage) + ", \"skipped\": true}");
      resetUploadState();
      return;
    }

    memcpy(pageStorage[uploadTargetPage], imageBuffer, IMAGE_BYTES);
    pageLoaded[uploadTargetPage] = true;
    saveSlotToFlash(uploadTargetPage);

    if (uploadTargetPage == currentPage) {
      showPage(currentPage);
    }

    server.send(200, "application/json",
      "{\"success\": true, \"page\": " + String(uploadTargetPage) + "}");
    resetUploadState();
    return;
  }

  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    display.drawBitmap(0, 0, imageBuffer, DISPLAY_WIDTH, DISPLAY_HEIGHT, GxEPD_BLACK);
    delay(1);
  } while (display.nextPage());
  display.hibernate();

  server.send(200, "application/json", "{\"success\": true, \"displayed\": true}");
  resetUploadState();
}

void handleClear() {
  markClientActivity();
  if (server.method() != HTTP_POST) {
    sendJsonError(405, "Method Not Allowed");
    return;
  }

  bool clearAll = false;
  int targetPage = currentPage;
  String body = server.arg("plain");

  if (body.length() > 0) {
    JsonDocument doc;
    if (deserializeJson(doc, body) != DeserializationError::Ok) {
      sendJsonError(400, "Invalid JSON");
      return;
    }

    if (doc["all"].is<bool>() && doc["all"].as<bool>()) {
      clearAll = true;
    } else if (doc["page"].is<int>()) {
      targetPage = doc["page"].as<int>();
      if (!isValidPageIndex(targetPage)) {
        sendJsonError(400, "Page out of range");
        return;
      }
    } else {
      sendJsonError(400, "Expected 'all' or 'page'");
      return;
    }
  }

  if (clearAll) {
    for (int i = 0; i < NUM_PAGES; i++) {
      clearStoredPage(i);
    }
    showBlankScreen();
  } else {
    clearStoredPage(targetPage);
    if (targetPage == currentPage) {
      showBlankScreen();
    }
  }

  JsonDocument resp;
  resp["success"] = true;
  resp["all"] = clearAll;
  resp["page"] = clearAll ? currentPage : targetPage;
  resp["loaded"] = false;
  appendCapabilityFields(resp);
  String response;
  serializeJson(resp, response);
  server.send(200, "application/json", response);
}

void handleNotFound() {
  markClientActivity();
  server.send(404, "application/json", "{\"error\": \"Not Found\"}");
}

void handleEventLog() {
  markClientActivity();
  JsonDocument doc;
  doc["magic_ok"] = (eventLogHeader.magic == EVENT_LOG_MAGIC);
  doc["write_index"] = eventLogHeader.write_index;
  doc["total_appended"] = eventLogHeader.total_appended;
  doc["capacity"] = EVENT_LOG_CAPACITY;
  JsonArray entries = doc["entries"].to<JsonArray>();
  // Emit in chronological order: oldest entry is at write_index when buffer
  // has wrapped; just before write_index for the most recent.
  for (int i = 0; i < EVENT_LOG_CAPACITY; i++) {
    int idx = (eventLogHeader.write_index + i) % EVENT_LOG_CAPACITY;
    const EventLogEntry& e = eventLogBuffer[idx];
    if (e.event_code == EVENT_NONE) continue;
    JsonObject obj = entries.add<JsonObject>();
    obj["ts_ms"] = e.ts_ms;
    obj["event"] = eventCodeName(e.event_code);
    obj["event_code"] = e.event_code;
    obj["reset_reason"] = resetReasonName(static_cast<esp_reset_reason_t>(e.reset_reason_code));
    obj["restart_count"] = e.restart_count;
    obj["extra1"] = e.extra1;
    obj["extra2"] = e.extra2;
    obj["battery_mv"] = e.battery_mv;
    obj["rssi_dbm"] = e.rssi_dbm;
    obj["free_heap_kb"] = e.free_heap_kb;
  }
  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void startMdns() {
  if (mdnsReady || WiFi.status() != WL_CONNECTED) return;
  if (MDNS.begin(HOSTNAME)) {
    MDNS.addService("http", "tcp", 80);
    mdnsReady = true;
    usbSerial.printf("mDNS ready: %s.local\n", HOSTNAME);
  } else {
    usbSerial.println("mDNS start failed");
  }
}

void startOta() {
  if (otaReady || WiFi.status() != WL_CONNECTED || strlen(OTA_PASSWORD) == 0) return;
  ArduinoOTA.setHostname(HOSTNAME);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.onStart([]() { usbSerial.println("OTA starting..."); });
  ArduinoOTA.onEnd([]() { usbSerial.println("OTA done!"); });
  ArduinoOTA.begin();
  otaReady = true;
  usbSerial.println("OTA ready");
}

void resetNetworkServices() {
  if (mdnsReady) {
    MDNS.end();
  }
  mdnsReady = false;
  otaReady = false;
}

void restartForHealth(SelfRestartReason reason) {
  lastSelfRestartReasonCode = static_cast<uint32_t>(reason);
  lastSelfRestartUptimeMs = millis();
  selfRestartCount++;
  uint8_t evt = EVENT_NONE;
  switch (reason) {
    case SELF_RESTART_PERIODIC:    evt = EVENT_RESTART_PERIODIC;    break;
    case SELF_RESTART_WIFI_STALE:  evt = EVENT_RESTART_WIFI_STALE;  break;
    case SELF_RESTART_HTTP_IDLE:   evt = EVENT_RESTART_HTTP_IDLE;   break;
    default: break;
  }
  if (evt != EVENT_NONE) {
    eventLogAppend(evt, lastSelfRestartUptimeMs, httpRequestCount);
  }
  usbSerial.printf(
    "Self-restarting: reason=%s uptime_ms=%lu count=%lu\n",
    selfRestartReasonName(lastSelfRestartReasonCode),
    static_cast<unsigned long>(lastSelfRestartUptimeMs),
    static_cast<unsigned long>(selfRestartCount)
  );
  delay(100);
  ESP.restart();
}

// === Battery-mode wake/poll/sleep helpers ===

// Decode first 8 hex chars of a sha256 string into a 32-bit fingerprint.
// We only need fingerprint comparison; full sha256 is more than necessary.
uint32_t hashFingerprint(const char* hex) {
  if (hex == nullptr || strlen(hex) < 8) return 0;
  char buf[9];
  memcpy(buf, hex, 8);
  buf[8] = 0;
  return static_cast<uint32_t>(strtoul(buf, nullptr, 16));
}

bool connectWifiBlocking(unsigned long timeout_ms) {
  if (strlen(WIFI_SSID) == 0) return false;
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(WIFI_PS_MIN_MODEM);
  WiFi.setHostname(HOSTNAME);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start >= timeout_ms) return false;
    delay(100);
  }
  lastWifiOkMs = millis();
  return true;
}

bool fetchSlotBitmap(int slot) {
  if (strlen(RETERMINAL_PUBLISHER_HOST) == 0) return false;
  if (pageStorage[slot] == nullptr) return false;

  String url = String("http://") + RETERMINAL_PUBLISHER_HOST + ":" +
               String(RETERMINAL_PUBLISHER_PORT) + "/content/slot-" + slot;
  WiFiClient client;
  HTTPClient http;
  if (!http.begin(client, url)) return false;
  http.setTimeout(10000);
  int code = http.GET();
  if (code != 200) {
    http.end();
    return false;
  }
  WiFiClient* stream = http.getStreamPtr();
  size_t got = 0;
  while (got < IMAGE_BYTES && (http.connected() || stream->available())) {
    int n = stream->readBytes(pageStorage[slot] + got, IMAGE_BYTES - got);
    if (n <= 0) break;
    got += n;
  }
  http.end();
  if (got != IMAGE_BYTES) return false;
  pageLoaded[slot] = true;
  saveSlotToFlash(slot);
  return true;
}

// Returns slots updated, -1 on error.
int wakePollAndUpdate() {
  if (strlen(RETERMINAL_PUBLISHER_HOST) == 0) return 0;

  String url = String("http://") + RETERMINAL_PUBLISHER_HOST + ":" +
               String(RETERMINAL_PUBLISHER_PORT) + "/content-hash";
  WiFiClient client;
  HTTPClient http;
  if (!http.begin(client, url)) return -1;
  http.setTimeout(5000);
  int code = http.GET();
  if (code != 200) {
    http.end();
    return -1;
  }
  String body = http.getString();
  http.end();

  JsonDocument doc;
  if (deserializeJson(doc, body) != DeserializationError::Ok) return -1;

  int updated = 0;
  for (int i = 0; i < NUM_PAGES; i++) {
    String key = "slot-" + String(i);
    const char* hash = doc["hashes"][key];
    uint32_t fp = hashFingerprint(hash);
    if (fp != 0 && fp != slotHashFingerprint[i]) {
      if (fetchSlotBitmap(i)) {
        slotHashFingerprint[i] = fp;
        updated++;
      }
    }
  }
  return updated;
}

bool isLongRightPress() {
  unsigned long start = millis();
  while (millis() - start < RETERMINAL_DIAGNOSTIC_HOLD_MS) {
    if (digitalRead(BTN_RIGHT) != LOW) return false;
    delay(50);
  }
  return digitalRead(BTN_RIGHT) == LOW;
}

void enterDeepSleep() {
  display.hibernate();
  digitalWrite(BATTERY_ENABLE_PIN, LOW);

  if (loopWatchdogArmed) {
    esp_task_wdt_delete(NULL);
    esp_task_wdt_deinit();
    loopWatchdogArmed = false;
  }

  WiFi.disconnect(true, true);
  WiFi.mode(WIFI_OFF);

  esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(RETERMINAL_WAKE_INTERVAL_S) * 1000000ULL);

  // EXT1 wake on any button going LOW. Each button pin is initialized as an
  // RTC GPIO input with pullup enabled, then handed to the EXT1 wake mux.
  // Skipping rtc_gpio_init leaves the pin in unknown state during deep sleep.
  gpio_num_t buttonPins[] = {
    static_cast<gpio_num_t>(BTN_LEFT),
    static_cast<gpio_num_t>(BTN_MIDDLE),
    static_cast<gpio_num_t>(BTN_RIGHT),
  };
  for (gpio_num_t pin : buttonPins) {
    rtc_gpio_init(pin);
    rtc_gpio_set_direction(pin, RTC_GPIO_MODE_INPUT_ONLY);
    rtc_gpio_pulldown_dis(pin);
    rtc_gpio_pullup_en(pin);
    rtc_gpio_hold_en(pin);
  }
  uint64_t mask = (1ULL << BTN_LEFT) | (1ULL << BTN_MIDDLE) | (1ULL << BTN_RIGHT);
  esp_sleep_enable_ext1_wakeup(mask, ESP_EXT1_WAKEUP_ANY_LOW);

  usbSerial.printf("Deep sleep: %lus or button. uptime=%lums\n",
                   static_cast<unsigned long>(RETERMINAL_WAKE_INTERVAL_S),
                   static_cast<unsigned long>(millis()));
  delay(50);
  esp_deep_sleep_start();
}

void registerHttpRoutes() {
  server.on("/", handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/capabilities", HTTP_GET, handleCapabilities);
  server.on("/snapshot", HTTP_GET, handleSnapshot);
  server.on("/buttons", HTTP_GET, handleButtons);
  server.on("/beep", HTTP_GET, handleBeep);
  server.on("/page", handlePage);
  server.on("/imageraw", HTTP_POST, handleImageRaw, handleImageUpload);
  server.on("/clear", HTTP_POST, handleClear);
  server.on("/eventlog", HTTP_GET, handleEventLog);
  server.onNotFound(handleNotFound);
}

void enterDiagnosticMode() {
  diagnosticMode = true;
  diagnosticEntryMs = millis();
  lastClientMs = millis();
  beep(200);
  WiFi.setSleep(false);
  registerHttpRoutes();
  server.begin();
  startMdns();
  startOta();
  loopWatchdogInitStatus = esp_task_wdt_init(LOOP_WDT_TIMEOUT_S, true);
  if (loopWatchdogInitStatus == ESP_OK || loopWatchdogInitStatus == ESP_ERR_INVALID_STATE) {
    loopWatchdogAddStatus = esp_task_wdt_add(NULL);
    loopWatchdogArmed = loopWatchdogAddStatus == ESP_OK || esp_task_wdt_status(NULL) == ESP_OK;
  }
  usbSerial.println("Diagnostic mode ON (10 min)");
}

void handleButtonWake() {
  uint64_t mask = esp_sleep_get_ext1_wakeup_status();
  if (mask & (1ULL << BTN_RIGHT)) {
    if (isLongRightPress()) {
      enterDiagnosticMode();
      return;
    }
    showPage(currentPage);
  } else if (mask & (1ULL << BTN_LEFT)) {
    currentPage = (currentPage - 1 + NUM_PAGES) % NUM_PAGES;
    showPage(currentPage);
    saveState();
    rtcVisibleSlot = currentPage;
  } else if (mask & (1ULL << BTN_MIDDLE)) {
    currentPage = (currentPage + 1) % NUM_PAGES;
    showPage(currentPage);
    saveState();
    rtcVisibleSlot = currentPage;
  }
}

void setup() {
  // reTerminal routes USB-serial through GPIO 44/43, not the default pins.
  usbSerial.begin(115200, SERIAL_8N1, 44, 43);
  delay(50);
  setCpuFrequencyMhz(80);

  esp_sleep_wakeup_cause_t wakeCause = esp_sleep_get_wakeup_cause();
  bool firstBoot = (rtcStateMagic != RTC_STATE_MAGIC);

  // Release the RTC hold we set before sleep, so pinMode / digitalRead work
  // again on this wake. Without this the buttons read stuck values.
  rtc_gpio_hold_dis(static_cast<gpio_num_t>(BTN_LEFT));
  rtc_gpio_hold_dis(static_cast<gpio_num_t>(BTN_MIDDLE));
  rtc_gpio_hold_dis(static_cast<gpio_num_t>(BTN_RIGHT));
  rtc_gpio_deinit(static_cast<gpio_num_t>(BTN_LEFT));
  rtc_gpio_deinit(static_cast<gpio_num_t>(BTN_MIDDLE));
  rtc_gpio_deinit(static_cast<gpio_num_t>(BTN_RIGHT));
  if (firstBoot) {
    rtcStateMagic = RTC_STATE_MAGIC;
    bootCount = 0;
    memset((void*)slotHashFingerprint, 0, sizeof(slotHashFingerprint));
    rtcVisibleSlot = 0;
  }
  bootCount++;
  usbSerial.printf("\nreTerminal wake cause=%d firstBoot=%d bootCount=%lu\n",
                   (int)wakeCause, firstBoot ? 1 : 0,
                   static_cast<unsigned long>(bootCount));

  if (esp_reset_reason() != ESP_RST_SW) {
    lastSelfRestartReasonCode = SELF_RESTART_NONE;
    lastSelfRestartUptimeMs = 0;
  }

  pinMode(BTN_LEFT, INPUT_PULLUP);
  pinMode(BTN_MIDDLE, INPUT_PULLUP);
  pinMode(BTN_RIGHT, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  lastLeft = digitalRead(BTN_LEFT);
  lastMiddle = digitalRead(BTN_MIDDLE);
  lastRight = digitalRead(BTN_RIGHT);

  // Enable the battery-monitor voltage divider on GPIO1.
  pinMode(BATTERY_ENABLE_PIN, OUTPUT);
  digitalWrite(BATTERY_ENABLE_PIN, HIGH);
  analogSetPinAttenuation(BATTERY_ADC_PIN, ADC_11db);

  // Auto-format on mount failure so a fresh partition self-heals into a usable
  // filesystem on first boot. Without this, a corrupted or empty LittleFS
  // partition leaves slots volatile permanently, breaking the watchdog reboot
  // recovery story.
  if (LittleFS.begin(true, "/littlefs", 10, "littlefs")) {
    fsReady = true;
    LittleFS.mkdir(SLOT_DIR);
    usbSerial.println("LittleFS ready");
    eventLogLoad();
    eventLogAppend(EVENT_BOOT, static_cast<uint32_t>(esp_reset_reason()),
                   lastSelfRestartReasonCode);
  } else {
    usbSerial.println("LittleFS mount AND format failed — slots volatile this boot");
  }

  // Page storage. Allocate in PSRAM; only memset the buffer if its slot file
  // is missing (loadSlotFromFlash overwrites otherwise).
  for (int i = 0; i < NUM_PAGES; i++) {
    pageStorage[i] = (uint8_t*)ps_malloc(IMAGE_BYTES);
    if (pageStorage[i] == nullptr) {
      pageStorage[i] = (uint8_t*)malloc(IMAGE_BYTES);
    }
  }
  int restoredCount = 0;
  for (int i = 0; i < NUM_PAGES; i++) {
    if (loadSlotFromFlash(i)) {
      restoredCount++;
    } else if (pageStorage[i] != nullptr) {
      memset(pageStorage[i], 0xFF, IMAGE_BYTES);
    }
  }
  currentPage = loadState();
  if (currentPage < 0 || currentPage >= NUM_PAGES) currentPage = rtcVisibleSlot;
  rtcVisibleSlot = currentPage;

  // Display init. initial=true only on first boot; subsequent wakes skip the
  // extra panel calibration sequence.
  hspi.begin(EPD_SCK_PIN, -1, EPD_MOSI_PIN, -1);
  display.epd2.selectSPI(hspi, SPISettings(2000000, MSBFIRST, SPI_MODE0));
  display.init(115200, firstBoot);
  display.setRotation(0);

  // Dispatch on wake reason.
  if (wakeCause == ESP_SLEEP_WAKEUP_EXT1) {
    handleButtonWake();
    if (diagnosticMode) {
      // setup() returns; loop() runs the diagnostic loop until timeout.
      return;
    }
    enterDeepSleep();  // never returns
    return;
  }

  if (wakeCause == ESP_SLEEP_WAKEUP_TIMER) {
    if (connectWifiBlocking(15000)) {
      int updated = wakePollAndUpdate();
      if (updated > 0) {
        showPage(currentPage);
      }
    }
    enterDeepSleep();
    return;
  }

  // Cold boot (poweron, brownout-style reset, or first ever).
  if (restoredCount > 0 && pageLoaded[currentPage]) {
    showPage(currentPage);
  } else {
    showBootScreen();
  }
  if (connectWifiBlocking(15000)) {
    if (restoredCount == 0 || !pageLoaded[currentPage]) {
      showReadyScreen(WiFi.localIP().toString());
    }
    int updated = wakePollAndUpdate();
    if (updated > 0) {
      showPage(currentPage);
    }
    beep(100);
  } else if (firstBoot) {
    showConfigRequiredScreen("WiFi connect failed", "Check platformio.local.ini");
  }
  enterDeepSleep();
}

// Reused by diagnostic mode only. Tracks online/offline transitions and
// restarts if the wifi driver fails to recover. In normal battery operation
// the device only briefly has WiFi up at all, so this never matters.
void maintainWifi() {
  if (strlen(WIFI_SSID) == 0) return;
  unsigned long now = millis();

  if (wifiLinkUp()) {
    lastWifiOkMs = now;
    if (lastWifiLostMs != 0) {
      usbSerial.println("WiFi restored: " + WiFi.localIP().toString());
      uint32_t downMs = now - lastWifiLostMs;
      lastWifiLostMs = 0;
      wifiReconnectAttempts++;
      lastWifiReconnectMs = now;
      eventLogAppend(EVENT_WIFI_RESTORED, downMs, wifiReconnectAttempts);
    }
    startMdns();
    startOta();
    return;
  }

  if (lastWifiLostMs == 0) {
    lastWifiLostMs = now;
    resetNetworkServices();
    usbSerial.printf("WiFi link lost: status=%d\n", WiFi.status());
    eventLogAppend(EVENT_WIFI_LOST, static_cast<uint32_t>(WiFi.status()), 0);
  }

  if (lastWifiOkMs > 0 && WIFI_SELF_RESTART_MS > 0 && wifiDownDurationMs(now) >= WIFI_SELF_RESTART_MS) {
    restartForHealth(SELF_RESTART_WIFI_STALE);
  }
}

void loop() {
  // Diagnostic mode only. Normal operation ends in enterDeepSleep() from
  // setup() and loop() is never reached.
  if (!diagnosticMode) {
    enterDeepSleep();
    return;
  }

  if (loopWatchdogArmed) esp_task_wdt_reset();

  if (millis() - diagnosticEntryMs >= RETERMINAL_DIAGNOSTIC_TIMEOUT_MS) {
    usbSerial.println("Diagnostic mode timeout, sleeping.");
    enterDeepSleep();
    return;
  }

  if (otaReady) ArduinoOTA.handle();
  server.handleClient();
  maintainWifi();

  bool curLeft = digitalRead(BTN_LEFT);
  if (curLeft != lastLeft) {
    delay(DEBOUNCE_MS);
    if (curLeft == LOW) {
      beep(100);
      currentPage = (currentPage - 1 + NUM_PAGES) % NUM_PAGES;
      showPage(currentPage);
      saveState();
      rtcVisibleSlot = currentPage;
    }
    lastLeft = curLeft;
  }

  bool curMiddle = digitalRead(BTN_MIDDLE);
  if (curMiddle != lastMiddle) {
    delay(DEBOUNCE_MS);
    if (curMiddle == LOW) {
      beep(100);
      currentPage = (currentPage + 1) % NUM_PAGES;
      showPage(currentPage);
      saveState();
      rtcVisibleSlot = currentPage;
    }
    lastMiddle = curMiddle;
  }

  bool curRight = digitalRead(BTN_RIGHT);
  if (curRight != lastRight) {
    delay(DEBOUNCE_MS);
    if (curRight == LOW) {
      beep(100);
      showPage(currentPage);
    }
    lastRight = curRight;
  }

  delay(10);
}
