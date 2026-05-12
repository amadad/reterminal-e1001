/*
 * reTerminal E1001 — deep-sleep + pull kitchen display.
 *
 * Wake (timer every RETERMINAL_WAKE_INTERVAL_S, or button via EXT1) →
 *   connect WiFi → GET <publisher>/content-hash → fetch only the slots
 *   whose hash changed → save to LittleFS → refresh ePaper → deep sleep.
 *
 * Long-press right button (3s) enters diagnostic mode: HTTP server +
 * mDNS + OTA up for 10 minutes, then back to deep sleep.
 *
 * Slots persist in LittleFS; per-slot content fingerprints persist in
 * RTC RAM across sleep so we only fetch what actually changed.
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
#include <esp_sleep.h>
#include <driver/rtc_io.h>

// ---- Build flags ----
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
#ifndef RETERMINAL_WAKE_INTERVAL_S
#define RETERMINAL_WAKE_INTERVAL_S 1800UL          // 30 min
#endif
#ifndef RETERMINAL_DIAGNOSTIC_HOLD_MS
#define RETERMINAL_DIAGNOSTIC_HOLD_MS 3000UL
#endif
#ifndef RETERMINAL_DIAGNOSTIC_TIMEOUT_MS
#define RETERMINAL_DIAGNOSTIC_TIMEOUT_MS 600000UL  // 10 min
#endif
#ifndef RETERMINAL_PUBLISHER_HOST
#define RETERMINAL_PUBLISHER_HOST ""
#endif
#ifndef RETERMINAL_PUBLISHER_PORT
#define RETERMINAL_PUBLISHER_PORT 8765
#endif

// ---- Pins / dimensions ----
#define EPD_SCK_PIN 7
#define EPD_MOSI_PIN 9
#define EPD_CS_PIN 10
#define EPD_DC_PIN 11
#define EPD_RES_PIN 12
#define EPD_BUSY_PIN 13
#define BTN_LEFT 5
#define BTN_MIDDLE 4
#define BTN_RIGHT 3
#define BUZZER_PIN 45
#define LED_PIN 6
#define BATTERY_ADC_PIN 1
#define BATTERY_ENABLE_PIN 21
#define DISPLAY_WIDTH 800
#define DISPLAY_HEIGHT 480
#define IMAGE_BYTES (DISPLAY_WIDTH * DISPLAY_HEIGHT / 8)

const int NUM_PAGES = 4;
const char* PAGE_NAMES[] = {"slot-0", "slot-1", "slot-2", "slot-3"};
const char* SLOT_DIR = "/slots";
const char* STATE_FILE = "/state.json";
const char* EVENT_LOG_PATH = "/eventlog.bin";

// ---- Runtime state ----
uint8_t* pageStorage[NUM_PAGES] = {nullptr};
bool pageLoaded[NUM_PAGES] = {false};
int currentPage = 0;
bool fsReady = false;
HardwareSerial& usbSerial = Serial1;

GxEPD2_BW<GxEPD2_750_GDEY075T7, GxEPD2_750_GDEY075T7::HEIGHT> display(
    GxEPD2_750_GDEY075T7(EPD_CS_PIN, EPD_DC_PIN, EPD_RES_PIN, EPD_BUSY_PIN));
SPIClass hspi(HSPI);
WebServer server(80);
uint8_t* uploadBuffer = nullptr;
size_t uploadBytesReceived = 0;
int uploadTargetPage = -1;

// ---- RTC state (survives deep sleep, lost on poweron) ----
const uint32_t RTC_MAGIC = 0x52455445;  // 'RETE'
RTC_DATA_ATTR uint32_t rtcMagic = 0;
RTC_DATA_ATTR uint32_t bootCount = 0;
RTC_DATA_ATTR uint32_t slotHash[NUM_PAGES] = {0};
RTC_DATA_ATTR int rtcVisibleSlot = 0;

// ---- Diagnostic mode (long-press right) ----
bool diagnosticMode = false;
unsigned long diagnosticEntryMs = 0;

// =====================================================================
// Event log — small ring buffer in LittleFS, post-mortem only.
// =====================================================================

enum EventCode : uint8_t {
  EVENT_NONE = 0,
  EVENT_BOOT = 1,
  EVENT_WAKE_TIMER = 2,
  EVENT_WAKE_BUTTON = 3,
  EVENT_DIAGNOSTIC = 4,
  EVENT_WIFI_FAIL = 5,
};

struct EventEntry {
  uint32_t ts_ms;
  uint8_t event_code;
  uint8_t reset_reason;
  uint16_t battery_mv;
  int16_t rssi_dbm;
  uint16_t free_heap_kb;
  uint32_t boot_count;
};  // 16 bytes

const int EVENT_LOG_CAPACITY = 32;
const uint32_t EVENT_LOG_MAGIC = 0x52454C49;  // 'RELI'

struct EventLogHeader {
  uint32_t magic;
  uint32_t write_index;
  uint32_t total_appended;
  uint32_t reserved;
};

EventLogHeader eventLogHeader = {EVENT_LOG_MAGIC, 0, 0, 0};
EventEntry eventLogBuffer[EVENT_LOG_CAPACITY] = {};

uint16_t readBatteryMv() {
  return static_cast<uint16_t>(analogReadMilliVolts(BATTERY_ADC_PIN) * 2);
}

void eventLogLoad() {
  if (!fsReady) return;
  File f = LittleFS.open(EVENT_LOG_PATH, "r");
  if (!f) return;
  size_t expected = sizeof(eventLogHeader) + sizeof(eventLogBuffer);
  if (f.size() != expected) { f.close(); return; }
  EventLogHeader hdr;
  if (f.read(reinterpret_cast<uint8_t*>(&hdr), sizeof(hdr)) != sizeof(hdr) ||
      hdr.magic != EVENT_LOG_MAGIC) { f.close(); return; }
  if (f.read(reinterpret_cast<uint8_t*>(eventLogBuffer), sizeof(eventLogBuffer)) !=
      sizeof(eventLogBuffer)) { f.close(); return; }
  f.close();
  eventLogHeader = hdr;
  if (eventLogHeader.write_index >= EVENT_LOG_CAPACITY) eventLogHeader.write_index = 0;
}

void eventLogAppend(uint8_t code) {
  if (!fsReady) return;
  EventEntry& slot = eventLogBuffer[eventLogHeader.write_index];
  slot.ts_ms = millis();
  slot.event_code = code;
  slot.reset_reason = static_cast<uint8_t>(esp_reset_reason());
  slot.battery_mv = readBatteryMv();
  slot.rssi_dbm = WiFi.RSSI();
  slot.free_heap_kb = static_cast<uint16_t>(ESP.getFreeHeap() / 1024);
  slot.boot_count = bootCount;
  eventLogHeader.write_index = (eventLogHeader.write_index + 1) % EVENT_LOG_CAPACITY;
  eventLogHeader.total_appended++;
  File f = LittleFS.open(EVENT_LOG_PATH, "w");
  if (!f) return;
  f.write(reinterpret_cast<const uint8_t*>(&eventLogHeader), sizeof(eventLogHeader));
  f.write(reinterpret_cast<const uint8_t*>(eventLogBuffer), sizeof(eventLogBuffer));
  f.close();
}

const char* eventName(uint8_t c) {
  switch (c) {
    case EVENT_BOOT: return "boot";
    case EVENT_WAKE_TIMER: return "wake_timer";
    case EVENT_WAKE_BUTTON: return "wake_button";
    case EVENT_DIAGNOSTIC: return "diagnostic";
    case EVENT_WIFI_FAIL: return "wifi_fail";
    default: return "none";
  }
}

// =====================================================================
// Display
// =====================================================================

void beep(int ms = 300) { tone(BUZZER_PIN, 1000, ms); }

void printCentered(const char* text, int y) {
  int16_t x1, y1; uint16_t w, h;
  display.getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
  display.setCursor((DISPLAY_WIDTH - w) / 2, y);
  display.print(text);
}

void showPage(int page) {
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    if (pageLoaded[page] && pageStorage[page]) {
      display.drawBitmap(0, 0, pageStorage[page], DISPLAY_WIDTH, DISPLAY_HEIGHT, GxEPD_BLACK);
    } else {
      display.setFont(&FreeMonoBold18pt7b);
      display.setTextColor(GxEPD_BLACK);
      printCentered(PAGE_NAMES[page], 200);
      printCentered("No image loaded", 260);
    }
    delay(1);
  } while (display.nextPage());
  display.hibernate();
}

void showCenteredScreen(const char* l1, const char* l2 = nullptr, const char* l3 = nullptr) {
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);
    display.setFont(&FreeMonoBold18pt7b);
    display.setTextColor(GxEPD_BLACK);
    printCentered(l1, l2 ? 180 : 240);
    if (l2) printCentered(l2, 240);
    if (l3) printCentered(l3, 300);
    delay(1);
  } while (display.nextPage());
  display.hibernate();
}

// =====================================================================
// Persistence
// =====================================================================

String slotPath(int page) {
  return String(SLOT_DIR) + "/slot-" + String(page) + ".raw";
}

void saveSlotToFlash(int page) {
  if (!fsReady || !pageLoaded[page] || !pageStorage[page]) return;
  File f = LittleFS.open(slotPath(page), "w");
  if (!f) return;
  f.write(pageStorage[page], IMAGE_BYTES);
  f.close();
}

bool loadSlotFromFlash(int page) {
  if (!fsReady || !pageStorage[page]) return false;
  File f = LittleFS.open(slotPath(page), "r");
  if (!f || f.size() != IMAGE_BYTES) { if (f) f.close(); return false; }
  f.read(pageStorage[page], IMAGE_BYTES);
  f.close();
  pageLoaded[page] = true;
  return true;
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
  if (deserializeJson(doc, f) != DeserializationError::Ok) { f.close(); return 0; }
  f.close();
  int page = doc["currentPage"] | 0;
  return (page < 0 || page >= NUM_PAGES) ? 0 : page;
}

// =====================================================================
// WiFi + HTTP pull
// =====================================================================

bool connectWifi(unsigned long timeout_ms) {
  if (strlen(RETERMINAL_WIFI_SSID) == 0) return false;
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(WIFI_PS_MIN_MODEM);
  WiFi.setHostname(RETERMINAL_HOSTNAME);
  WiFi.begin(RETERMINAL_WIFI_SSID, RETERMINAL_WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start >= timeout_ms) return false;
    delay(100);
  }
  return true;
}

uint32_t hashFingerprint(const char* hex) {
  if (!hex || strlen(hex) < 8) return 0;
  char buf[9];
  memcpy(buf, hex, 8); buf[8] = 0;
  return static_cast<uint32_t>(strtoul(buf, nullptr, 16));
}

String publisherBase() {
  return String("http://") + RETERMINAL_PUBLISHER_HOST + ":" +
         String(RETERMINAL_PUBLISHER_PORT);
}

// Returns slots updated (>=0), or -1 on hash-endpoint failure.
int wakePoll() {
  if (strlen(RETERMINAL_PUBLISHER_HOST) == 0) return -1;
  WiFiClient client; HTTPClient http;
  if (!http.begin(client, publisherBase() + "/content-hash")) return -1;
  http.setTimeout(5000);
  if (http.GET() != 200) { http.end(); return -1; }
  JsonDocument doc;
  if (deserializeJson(doc, http.getString()) != DeserializationError::Ok) {
    http.end(); return -1;
  }
  http.end();

  int updated = 0;
  for (int i = 0; i < NUM_PAGES; i++) {
    uint32_t fp = hashFingerprint(doc["hashes"][String("slot-") + i]);
    if (fp == 0 || fp == slotHash[i] || !pageStorage[i]) continue;
    HTTPClient h2;
    if (!h2.begin(client, publisherBase() + "/content/slot-" + i)) continue;
    h2.setTimeout(10000);
    if (h2.GET() != 200) { h2.end(); continue; }
    WiFiClient* s = h2.getStreamPtr();
    size_t got = 0;
    while (got < IMAGE_BYTES && (h2.connected() || s->available())) {
      int n = s->readBytes(pageStorage[i] + got, IMAGE_BYTES - got);
      if (n <= 0) break;
      got += n;
    }
    h2.end();
    if (got != IMAGE_BYTES) continue;
    pageLoaded[i] = true;
    saveSlotToFlash(i);
    slotHash[i] = fp;
    updated++;
  }
  return updated;
}

// =====================================================================
// Deep sleep + button wake
// =====================================================================

void enterDeepSleep() {
  display.hibernate();
  digitalWrite(BATTERY_ENABLE_PIN, LOW);
  WiFi.disconnect(true, true);
  WiFi.mode(WIFI_OFF);

  esp_sleep_enable_timer_wakeup(
      static_cast<uint64_t>(RETERMINAL_WAKE_INTERVAL_S) * 1000000ULL);

  gpio_num_t pins[] = {(gpio_num_t)BTN_LEFT, (gpio_num_t)BTN_MIDDLE, (gpio_num_t)BTN_RIGHT};
  for (gpio_num_t pin : pins) {
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

bool isLongRightPress() {
  unsigned long start = millis();
  while (millis() - start < RETERMINAL_DIAGNOSTIC_HOLD_MS) {
    if (digitalRead(BTN_RIGHT) != LOW) return false;
    delay(50);
  }
  return digitalRead(BTN_RIGHT) == LOW;
}

void handleButtonWake() {
  uint64_t mask = esp_sleep_get_ext1_wakeup_status();
  if (mask & (1ULL << BTN_RIGHT)) {
    if (isLongRightPress()) {
      diagnosticMode = true;
      return;
    }
    showPage(currentPage);
  } else if (mask & (1ULL << BTN_LEFT)) {
    currentPage = (currentPage - 1 + NUM_PAGES) % NUM_PAGES;
    rtcVisibleSlot = currentPage;
    showPage(currentPage);
    saveState();
  } else if (mask & (1ULL << BTN_MIDDLE)) {
    currentPage = (currentPage + 1) % NUM_PAGES;
    rtcVisibleSlot = currentPage;
    showPage(currentPage);
    saveState();
  }
}

// =====================================================================
// Diagnostic mode HTTP API (only registered when entered)
// =====================================================================

void sendJson(int code, const String& body) {
  server.send(code, "application/json", body);
}

void handleStatus() {
  JsonDocument doc;
  doc["ip"] = WiFi.localIP().toString();
  doc["ssid"] = WiFi.SSID();
  doc["rssi"] = WiFi.RSSI();
  doc["hostname"] = RETERMINAL_HOSTNAME;
  doc["firmware_version"] = RETERMINAL_FIRMWARE_VERSION;
  doc["build_sha"] = RETERMINAL_BUILD_SHA;
  doc["build_time"] = __DATE__ " " __TIME__;
  doc["uptime_ms"] = millis();
  doc["free_heap"] = ESP.getFreeHeap();
  doc["free_psram"] = ESP.getFreePsram();
  doc["boot_count"] = bootCount;
  doc["wake_interval_s"] = RETERMINAL_WAKE_INTERVAL_S;
  doc["diagnostic_timeout_ms"] = RETERMINAL_DIAGNOSTIC_TIMEOUT_MS;
  doc["battery_mv"] = readBatteryMv();
  doc["page_slots"] = NUM_PAGES;
  doc["current_page"] = currentPage;
  doc["reset_reason"] = static_cast<int>(esp_reset_reason());
  doc["littlefs_used_bytes"] = fsReady ? LittleFS.usedBytes() : 0;
  doc["event_log_total"] = eventLogHeader.total_appended;
  JsonArray loaded = doc["loaded_pages"].to<JsonArray>();
  for (int i = 0; i < NUM_PAGES; i++) loaded.add(pageLoaded[i]);
  String body; serializeJson(doc, body);
  sendJson(200, body);
}

void handleEventLog() {
  JsonDocument doc;
  doc["total_appended"] = eventLogHeader.total_appended;
  doc["capacity"] = EVENT_LOG_CAPACITY;
  JsonArray entries = doc["entries"].to<JsonArray>();
  for (int i = 0; i < EVENT_LOG_CAPACITY; i++) {
    int idx = (eventLogHeader.write_index + i) % EVENT_LOG_CAPACITY;
    const EventEntry& e = eventLogBuffer[idx];
    if (e.event_code == EVENT_NONE) continue;
    JsonObject o = entries.add<JsonObject>();
    o["ts_ms"] = e.ts_ms;
    o["event"] = eventName(e.event_code);
    o["reset_reason"] = e.reset_reason;
    o["battery_mv"] = e.battery_mv;
    o["rssi_dbm"] = e.rssi_dbm;
    o["free_heap_kb"] = e.free_heap_kb;
    o["boot_count"] = e.boot_count;
  }
  String body; serializeJson(doc, body);
  sendJson(200, body);
}

void handleSnapshot() {
  int page = currentPage;
  String arg = server.arg("page");
  if (arg.length() > 0) page = arg.toInt();
  if (page < 0 || page >= NUM_PAGES || !pageLoaded[page] || !pageStorage[page]) {
    sendJson(404, "{\"error\":\"no bitmap\"}");
    return;
  }
  server.sendHeader("Content-Type", "application/octet-stream");
  server.setContentLength(IMAGE_BYTES);
  server.send(200, "application/octet-stream", "");
  server.client().write(pageStorage[page], IMAGE_BYTES);
}

void handleImageUpload() {
  HTTPUpload& upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    uploadBytesReceived = 0;
    String arg = server.arg("page");
    uploadTargetPage = (arg.length() > 0) ? arg.toInt() : -1;
    if (!uploadBuffer) {
      uploadBuffer = (uint8_t*)ps_malloc(IMAGE_BYTES);
      if (!uploadBuffer) uploadBuffer = (uint8_t*)malloc(IMAGE_BYTES);
    }
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (uploadBuffer && uploadBytesReceived + upload.currentSize <= IMAGE_BYTES) {
      memcpy(uploadBuffer + uploadBytesReceived, upload.buf, upload.currentSize);
      uploadBytesReceived += upload.currentSize;
    }
  }
}

void handleImageRaw() {
  if (uploadTargetPage < 0 || uploadTargetPage >= NUM_PAGES) {
    sendJson(400, "{\"error\":\"bad page\"}");
    return;
  }
  if (uploadBytesReceived != IMAGE_BYTES || !uploadBuffer ||
      !pageStorage[uploadTargetPage]) {
    sendJson(400, "{\"error\":\"bad upload\"}");
    return;
  }
  memcpy(pageStorage[uploadTargetPage], uploadBuffer, IMAGE_BYTES);
  pageLoaded[uploadTargetPage] = true;
  saveSlotToFlash(uploadTargetPage);
  if (uploadTargetPage == currentPage) showPage(currentPage);
  sendJson(200, "{\"success\":true,\"page\":" + String(uploadTargetPage) + "}");
}

void handlePage() {
  if (server.method() == HTTP_GET) {
    sendJson(200, "{\"page\":" + String(currentPage) + ",\"total\":" + String(NUM_PAGES) + "}");
    return;
  }
  JsonDocument doc;
  if (deserializeJson(doc, server.arg("plain")) != DeserializationError::Ok) {
    sendJson(400, "{\"error\":\"bad json\"}");
    return;
  }
  int page = doc["page"] | -1;
  if (page < 0 || page >= NUM_PAGES) {
    sendJson(400, "{\"error\":\"bad page\"}");
    return;
  }
  currentPage = page;
  rtcVisibleSlot = page;
  showPage(currentPage);
  saveState();
  sendJson(200, "{\"page\":" + String(currentPage) + "}");
}

void handleSleep() {
  sendJson(200, "{\"sleeping\":true}");
  delay(100);
  enterDeepSleep();
}

void enterDiagnosticMode() {
  diagnosticEntryMs = millis();
  WiFi.setSleep(false);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/eventlog", HTTP_GET, handleEventLog);
  server.on("/snapshot", HTTP_GET, handleSnapshot);
  server.on("/imageraw", HTTP_POST, handleImageRaw, handleImageUpload);
  server.on("/page", handlePage);
  server.on("/sleep", HTTP_POST, handleSleep);
  server.onNotFound([](){ sendJson(404, "{\"error\":\"not found\"}"); });
  server.begin();
  if (MDNS.begin(RETERMINAL_HOSTNAME)) MDNS.addService("http", "tcp", 80);
  if (strlen(RETERMINAL_OTA_PASSWORD) > 0) {
    ArduinoOTA.setHostname(RETERMINAL_HOSTNAME);
    ArduinoOTA.setPassword(RETERMINAL_OTA_PASSWORD);
    ArduinoOTA.begin();
  }
  beep(200);
  eventLogAppend(EVENT_DIAGNOSTIC);
  usbSerial.printf("Diagnostic mode (%lus). Endpoints up at IP %s\n",
                   static_cast<unsigned long>(RETERMINAL_DIAGNOSTIC_TIMEOUT_MS / 1000),
                   WiFi.localIP().toString().c_str());
}

// =====================================================================
// setup / loop
// =====================================================================

void setup() {
  usbSerial.begin(115200, SERIAL_8N1, 44, 43);
  delay(50);
  setCpuFrequencyMhz(80);

  esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
  bool firstBoot = (rtcMagic != RTC_MAGIC);
  if (firstBoot) {
    rtcMagic = RTC_MAGIC;
    bootCount = 0;
    memset(reinterpret_cast<void*>(slotHash), 0, sizeof(slotHash));
    rtcVisibleSlot = 0;
  }
  bootCount++;
  usbSerial.printf("\nWake cause=%d firstBoot=%d bootCount=%lu\n",
                   (int)cause, firstBoot ? 1 : 0,
                   static_cast<unsigned long>(bootCount));

  // Un-hold the RTC pins from the previous sleep so pinMode + digitalRead work.
  for (gpio_num_t pin : {(gpio_num_t)BTN_LEFT, (gpio_num_t)BTN_MIDDLE, (gpio_num_t)BTN_RIGHT}) {
    rtc_gpio_hold_dis(pin);
    rtc_gpio_deinit(pin);
  }

  pinMode(BTN_LEFT, INPUT_PULLUP);
  pinMode(BTN_MIDDLE, INPUT_PULLUP);
  pinMode(BTN_RIGHT, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  pinMode(BATTERY_ENABLE_PIN, OUTPUT);
  digitalWrite(BATTERY_ENABLE_PIN, HIGH);
  analogSetPinAttenuation(BATTERY_ADC_PIN, ADC_11db);

  if (LittleFS.begin(true, "/littlefs", 10, "littlefs")) {
    fsReady = true;
    LittleFS.mkdir(SLOT_DIR);
    eventLogLoad();
    eventLogAppend(cause == ESP_SLEEP_WAKEUP_TIMER  ? EVENT_WAKE_TIMER
                   : cause == ESP_SLEEP_WAKEUP_EXT1 ? EVENT_WAKE_BUTTON
                                                   : EVENT_BOOT);
  }

  for (int i = 0; i < NUM_PAGES; i++) {
    pageStorage[i] = (uint8_t*)ps_malloc(IMAGE_BYTES);
    if (!pageStorage[i]) pageStorage[i] = (uint8_t*)malloc(IMAGE_BYTES);
  }
  for (int i = 0; i < NUM_PAGES; i++) {
    if (!loadSlotFromFlash(i) && pageStorage[i]) memset(pageStorage[i], 0xFF, IMAGE_BYTES);
  }
  currentPage = loadState();
  if (currentPage < 0 || currentPage >= NUM_PAGES) currentPage = rtcVisibleSlot;
  rtcVisibleSlot = currentPage;

  hspi.begin(EPD_SCK_PIN, -1, EPD_MOSI_PIN, -1);
  display.epd2.selectSPI(hspi, SPISettings(2000000, MSBFIRST, SPI_MODE0));
  display.init(115200, firstBoot);
  display.setRotation(0);

  // ---- Wake dispatch ----

  if (cause == ESP_SLEEP_WAKEUP_EXT1) {
    handleButtonWake();
    if (diagnosticMode) {
      // Need WiFi for the HTTP API in diagnostic mode.
      if (!connectWifi(15000)) {
        eventLogAppend(EVENT_WIFI_FAIL);
        enterDeepSleep();
        return;
      }
      enterDiagnosticMode();
      return;  // setup returns; loop() services HTTP + OTA until timeout.
    }
    enterDeepSleep();
    return;
  }

  if (cause == ESP_SLEEP_WAKEUP_TIMER) {
    if (connectWifi(15000)) {
      int updated = wakePoll();
      if (updated > 0) showPage(currentPage);
    } else {
      eventLogAppend(EVENT_WIFI_FAIL);
    }
    enterDeepSleep();
    return;
  }

  // Cold boot (poweron / brownout / first ever / SW reset).
  bool anyLoaded = false;
  for (int i = 0; i < NUM_PAGES; i++) if (pageLoaded[i]) { anyLoaded = true; break; }
  if (anyLoaded && pageLoaded[currentPage]) {
    showPage(currentPage);
  } else {
    showCenteredScreen("reTerminal E1001", "Connecting...");
  }
  if (connectWifi(15000)) {
    if (!anyLoaded) {
      showCenteredScreen("reTerminal E1001", "Ready!", WiFi.localIP().toString().c_str());
    }
    int updated = wakePoll();
    if (updated > 0) showPage(currentPage);
    beep(100);
  } else if (firstBoot) {
    showCenteredScreen("WiFi connect failed", "Check platformio.local.ini");
    eventLogAppend(EVENT_WIFI_FAIL);
  }
  enterDeepSleep();
}

void loop() {
  // Normal cycles never reach here; setup() always ends in enterDeepSleep().
  // Diagnostic mode runs this loop for RETERMINAL_DIAGNOSTIC_TIMEOUT_MS then
  // sleeps.
  if (!diagnosticMode) {
    enterDeepSleep();
    return;
  }
  if (millis() - diagnosticEntryMs >= RETERMINAL_DIAGNOSTIC_TIMEOUT_MS) {
    usbSerial.println("Diagnostic mode timeout — sleeping.");
    enterDeepSleep();
    return;
  }
  ArduinoOTA.handle();
  server.handleClient();
  delay(10);
}
