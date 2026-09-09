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
 * Slots persist in LittleFS. Full hashes are recomputed from stored bytes
 * on wake; delivery receipts follow pulls and returned display refresh calls.
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
#include <mbedtls/sha256.h>
#include <sys/time.h>
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
char storedHashes[NUM_PAGES][65] = {};
bool refreshReturned = false;
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
const uint32_t RTC_MAGIC = 0x52455447;  // RTC layout includes display hash and poll deadline
RTC_DATA_ATTR uint32_t rtcMagic = 0;
RTC_DATA_ATTR uint32_t bootCount = 0;
RTC_DATA_ATTR char rtcDisplayedHash[65] = {};
RTC_DATA_ATTR int rtcVisibleSlot = 0;
RTC_DATA_ATTR int64_t nextPollAtUs = 0;

// ---- Diagnostic mode (long-press right) ----
bool diagnosticMode = false;
unsigned long diagnosticEntryMs = 0;
const char* wakeReason = "boot";
String pullOutcome = "not_attempted";
String pullError;
String slotErrors[NUM_PAGES];

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
  EVENT_PULL_UPDATED = 6,
  EVENT_PULL_UNCHANGED = 7,
  EVENT_PULL_PARTIAL = 8,
  EVENT_PULL_ERROR = 9,
  EVENT_RECEIPT_FAIL = 10,
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
    case EVENT_PULL_UPDATED: return "pull_updated";
    case EVENT_PULL_UNCHANGED: return "pull_unchanged";
    case EVENT_PULL_PARTIAL: return "pull_partial";
    case EVENT_PULL_ERROR: return "pull_error";
    case EVENT_RECEIPT_FAIL: return "receipt_fail";
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
  refreshReturned = true;
  strlcpy(rtcDisplayedHash, pageLoaded[page] ? storedHashes[page] : "", sizeof(rtcDisplayedHash));
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
  rtcDisplayedHash[0] = 0;
}

// =====================================================================
// Persistence
// =====================================================================

String slotPath(int page) {
  return String(SLOT_DIR) + "/slot-" + String(page) + ".raw";
}

bool bitmapHash(const uint8_t* data, char* hex) {
  uint8_t digest[32];
  if (mbedtls_sha256_ret(data, IMAGE_BYTES, digest, 0) != 0) return false;
  for (int i = 0; i < 32; i++) snprintf(hex + i * 2, 3, "%02x", digest[i]);
  return true;
}

// Stage and verify before replacing the last good file or in-memory page.
bool saveSlotToFlash(int page, const uint8_t* data) {
  if (!fsReady || !data || !pageStorage[page]) return false;
  String temporary = slotPath(page) + ".tmp";
  File f = LittleFS.open(temporary, "w");
  if (!f) return false;
  size_t written = f.write(data, IMAGE_BYTES);
  f.close();
  bool valid = written == IMAGE_BYTES;
  f = LittleFS.open(temporary, "r");
  valid = valid && f && f.size() == IMAGE_BYTES;
  uint8_t chunk[1024];
  for (size_t offset = 0; valid && offset < IMAGE_BYTES; offset += sizeof(chunk)) {
    size_t count = min(sizeof(chunk), static_cast<size_t>(IMAGE_BYTES) - offset);
    valid = f.read(chunk, count) == count && memcmp(chunk, data + offset, count) == 0;
  }
  if (f) f.close();
  char digest[65];
  if (!valid || !bitmapHash(data, digest) || !LittleFS.rename(temporary, slotPath(page))) {
    LittleFS.remove(temporary);
    return false;
  }
  memcpy(pageStorage[page], data, IMAGE_BYTES);
  pageLoaded[page] = true;
  strlcpy(storedHashes[page], digest, sizeof(storedHashes[page]));
  return true;
}

bool loadSlotFromFlash(int page) {
  if (!fsReady || !pageStorage[page]) return false;
  File f = LittleFS.open(slotPath(page), "r");
  if (!f || f.size() != IMAGE_BYTES) { if (f) f.close(); return false; }
  size_t read = f.read(pageStorage[page], IMAGE_BYTES);
  f.close();
  if (read != IMAGE_BYTES || !bitmapHash(pageStorage[page], storedHashes[page])) return false;
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

// The configured RTC + high-resolution system clock survives deep sleep.
// No SNTP is used: these relative deadlines do not require calendar time.
int64_t clockUs() {
  timeval now;
  gettimeofday(&now, nullptr);
  return static_cast<int64_t>(now.tv_sec) * 1000000LL + now.tv_usec;
}

void scheduleNextPoll() {
  nextPollAtUs = clockUs() + static_cast<int64_t>(RETERMINAL_WAKE_INTERVAL_S) * 1000000LL;
}

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

bool validHash(const char* hex) {
  if (!hex || strlen(hex) != 64) return false;
  for (int i = 0; i < 64; i++) {
    if (!((hex[i] >= '0' && hex[i] <= '9') || (hex[i] >= 'a' && hex[i] <= 'f'))) return false;
  }
  return true;
}

String publisherBase() {
  return String("http://") + RETERMINAL_PUBLISHER_HOST + ":" +
         String(RETERMINAL_PUBLISHER_PORT);
}

// Stream::readBytes resets its timeout for each byte. Use an absolute body
// deadline so a stalled or trickling response cannot prolong this read forever.
size_t readBodyWithin(HTTPClient& http, uint8_t* destination, size_t expected,
                      unsigned long timeoutMs) {
  WiFiClient* stream = http.getStreamPtr();
  unsigned long started = millis();
  size_t got = 0;
  while (got < expected && millis() - started < timeoutMs) {
    int available = stream->available();
    if (available > 0) {
      size_t count = min(static_cast<size_t>(available), expected - got);
      int read = stream->read(destination + got, count);
      if (read <= 0) break;
      got += read;
    } else if (!http.connected()) {
      break;
    } else {
      delay(1);
    }
  }
  return got;
}

// Errors never replace the last good bitmap. Return the number of updated slots.
int wakePoll() {
  pullOutcome = "error";
  pullError = "";
  for (int i = 0; i < NUM_PAGES; i++) slotErrors[i] = "";
  if (strlen(RETERMINAL_PUBLISHER_HOST) == 0) {
    pullError = "publisher_not_configured";
    return 0;
  }
  WiFiClient client; HTTPClient http;
  if (!http.begin(client, publisherBase() + "/content-hash")) {
    pullError = "hash_connect_failed";
    return 0;
  }
  http.setTimeout(5000);
  int status = http.GET();
  if (status != 200) {
    pullError = String("hash_http_") + status;
    http.end();
    return 0;
  }
  int bodySize = http.getSize();
  if (bodySize <= 0 || bodySize > 4096) {
    pullError = "invalid_hash_manifest_length";
    http.end();
    return 0;
  }
  uint8_t* body = static_cast<uint8_t*>(malloc(bodySize));
  if (!body || readBodyWithin(http, body, bodySize, 5000) != static_cast<size_t>(bodySize)) {
    if (body) free(body);
    pullError = body ? "incomplete_hash_manifest" : "out_of_memory";
    http.end();
    return 0;
  }
  JsonDocument doc;
  DeserializationError parsed = deserializeJson(doc, static_cast<const uint8_t*>(body), bodySize);
  free(body);
  http.end();
  if (parsed != DeserializationError::Ok || !doc["hashes"].is<JsonObject>()) {
    pullError = "invalid_hash_manifest";
    return 0;
  }

  int updated = 0;
  int failures = 0;
  uint8_t* candidate = nullptr;
  for (int i = 0; i < NUM_PAGES; i++) {
    JsonObject hashes = doc["hashes"].as<JsonObject>();
    // An explicit null is an unassigned slot, not a deletion request. Keep its
    // last good bitmap; retiring visible content requires a rendered fallback.
    if (!hashes[PAGE_NAMES[i]].isUnbound() && hashes[PAGE_NAMES[i]].isNull()) continue;
    const char* desired = hashes[PAGE_NAMES[i]];
    if (!validHash(desired)) {
      slotErrors[i] = "invalid_hash";
      failures++;
      continue;
    }
    if (pageLoaded[i] && strcmp(desired, storedHashes[i]) == 0) continue;
    if (!candidate) candidate = static_cast<uint8_t*>(ps_malloc(IMAGE_BYTES));
    if (!candidate) candidate = static_cast<uint8_t*>(malloc(IMAGE_BYTES));
    if (!candidate || !pageStorage[i]) {
      slotErrors[i] = "out_of_memory";
      failures++;
      continue;
    }
    HTTPClient content;
    if (!content.begin(client, publisherBase() + "/content/" + PAGE_NAMES[i] + "?hash=" + desired)) {
      slotErrors[i] = "connect_failed";
      failures++;
      continue;
    }
    content.setTimeout(10000);
    status = content.GET();
    if (status != 200 || content.getSize() != IMAGE_BYTES) {
      slotErrors[i] = status != 200 ? String("http_") + status : "invalid_length";
      content.end();
      failures++;
      continue;
    }
    size_t got = readBodyWithin(content, candidate, IMAGE_BYTES, 10000);
    content.end();
    char actual[65];
    if (got != IMAGE_BYTES) slotErrors[i] = "incomplete_download";
    else if (!bitmapHash(candidate, actual) || strcmp(actual, desired) != 0) slotErrors[i] = "hash_mismatch";
    else if (!saveSlotToFlash(i, candidate)) slotErrors[i] = "storage_write_failed";
    else { updated++; continue; }
    failures++;
  }
  if (candidate) free(candidate);
  pullOutcome = failures ? (updated ? "partial" : "error") : (updated ? "updated" : "unchanged");
  if (failures) pullError = "slot_update_failed";
  return updated;
}

void addDeliveryState(JsonDocument& doc) {
  doc["device_id"] = WiFi.macAddress();
  doc["wake_reason"] = wakeReason;
  int64_t remaining = (nextPollAtUs - clockUs()) / 1000000LL;
  doc["next_poll_in_s"] = remaining > 0 ? remaining : 0;
  doc["outcome"] = pullOutcome;
  if (pullError.length()) doc["error"] = pullError;
  else doc["error"] = nullptr;
  doc["refresh_returned"] = refreshReturned;
  if (rtcDisplayedHash[0]) doc["displayed_hash"] = rtcDisplayedHash;
  else doc["displayed_hash"] = nullptr;
  JsonObject hashes = doc["hashes"].to<JsonObject>();
  JsonObject errors = doc["slot_errors"].to<JsonObject>();
  for (int i = 0; i < NUM_PAGES; i++) {
    if (pageLoaded[i]) hashes[PAGE_NAMES[i]] = storedHashes[i];
    else hashes[PAGE_NAMES[i]] = nullptr;
    if (slotErrors[i].length()) errors[PAGE_NAMES[i]] = slotErrors[i];
  }
}

void postReceipt() {
  if (strlen(RETERMINAL_PUBLISHER_HOST) == 0) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["hostname"] = RETERMINAL_HOSTNAME;
  doc["firmware_version"] = RETERMINAL_FIRMWARE_VERSION;
  doc["build_sha"] = RETERMINAL_BUILD_SHA;
  doc["boot_count"] = bootCount;
  doc["wake_interval_s"] = RETERMINAL_WAKE_INTERVAL_S;
  doc["current_page"] = currentPage;
  doc["uptime_ms"] = millis();
  doc["battery_mv"] = readBatteryMv();
  doc["rssi"] = WiFi.RSSI();
  addDeliveryState(doc);
  String body;
  serializeJson(doc, body);
  WiFiClient client; HTTPClient http;
  bool acknowledged = false;
  if (http.begin(client, publisherBase() + "/receipt")) {
    http.setTimeout(5000);
    http.addHeader("Content-Type", "application/json");
    int status = http.POST(body);
    acknowledged = status >= 200 && status < 300;
    http.end();
  }
  if (!acknowledged) eventLogAppend(EVENT_RECEIPT_FAIL);
}

void pullAndReport() {
  int updated = wakePoll();
  if (updated > 0) showPage(currentPage);
  eventLogAppend(pullOutcome == "updated" ? EVENT_PULL_UPDATED
                 : pullOutcome == "unchanged" ? EVENT_PULL_UNCHANGED
                 : pullOutcome == "partial" ? EVENT_PULL_PARTIAL : EVENT_PULL_ERROR);
  postReceipt();
}

// =====================================================================
// Deep sleep + button wake
// =====================================================================

void enterDeepSleep() {
  display.hibernate();
  digitalWrite(BATTERY_ENABLE_PIN, LOW);
  WiFi.disconnect(true, true);
  WiFi.mode(WIFI_OFF);

  int64_t now = clockUs();
  int64_t interval = static_cast<int64_t>(RETERMINAL_WAKE_INTERVAL_S) * 1000000LL;
  // Keep the original deadline through navigation wakes. A due poll wakes in
  // one second, after this button interaction, instead of being postponed.
  if (nextPollAtUs <= 0 || nextPollAtUs > now + interval) scheduleNextPoll();
  int64_t remaining = nextPollAtUs - now;
  uint64_t sleepUs = remaining > 1000000LL ? remaining : 1000000ULL;
  esp_sleep_enable_timer_wakeup(sleepUs);

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
                   static_cast<unsigned long>(sleepUs / 1000000ULL),
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
  addDeliveryState(doc);
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
  if (!saveSlotToFlash(uploadTargetPage, uploadBuffer)) {
    sendJson(500, "{\"error\":\"slot write failed\"}");
    return;
  }
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
    rtcDisplayedHash[0] = 0;
    rtcVisibleSlot = 0;
    nextPollAtUs = 0;
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
      // Need WiFi for the fresh pull and HTTP API in diagnostic mode.
      scheduleNextPoll();
      if (!connectWifi(15000)) {
        eventLogAppend(EVENT_WIFI_FAIL);
        enterDeepSleep();
        return;
      }
      wakeReason = "diagnostic";
      pullAndReport();
      enterDiagnosticMode();
      return;  // setup returns; loop() services HTTP + OTA until timeout.
    }
    enterDeepSleep();
    return;
  }

  if (cause == ESP_SLEEP_WAKEUP_TIMER) {
    scheduleNextPoll();
    if (connectWifi(15000)) {
      wakeReason = "timer";
      pullAndReport();
    } else {
      eventLogAppend(EVENT_WIFI_FAIL);
    }
    enterDeepSleep();
    return;
  }

  // Cold boot (poweron / brownout / first ever / SW reset).
  scheduleNextPoll();
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
    pullAndReport();
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
