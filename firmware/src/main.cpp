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
 *   POST /clear         - Clear one slot or the full volatile cache
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoOTA.h>
#include <ArduinoJson.h>
#include <GxEPD2_BW.h>
#include <Fonts/FreeMonoBold18pt7b.h>
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

// Button state tracking
bool lastLeft = HIGH, lastMiddle = HIGH, lastRight = HIGH;
unsigned long lastButtonPress = 0;
const unsigned long DEBOUNCE_MS = 50;

// Display and SPI objects
GxEPD2_BW<GxEPD2_750_GDEY075T7, GxEPD2_750_GDEY075T7::HEIGHT> display(
    GxEPD2_750_GDEY075T7(EPD_CS_PIN, EPD_DC_PIN, EPD_RES_PIN, EPD_BUSY_PIN));
SPIClass hspi(HSPI);

// Web server
WebServer server(80);

// Image buffer for uploads
uint8_t* imageBuffer = nullptr;

// USB Serial (per working example)
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

void showPage(int page) {
  display.setFullWindow();
  display.firstPage();
  do {
    display.fillScreen(GxEPD_WHITE);

    if (pageLoaded[page] && pageStorage[page] != nullptr) {
      // Draw stored bitmap
      display.drawBitmap(0, 0, pageStorage[page], DISPLAY_WIDTH, DISPLAY_HEIGHT, GxEPD_BLACK);
    } else {
      // Draw placeholder
      display.setFont(&FreeMonoBold18pt7b);
      display.setTextColor(GxEPD_BLACK);
      String title = String(PAGE_NAMES[page]);
      title.toUpperCase();
      printCentered(title.c_str(), 200);
      printCentered("No image loaded", 260);
    }

    // Render the stored bitmap truthfully with no firmware overlay chrome.

  } while (display.nextPage());

  usbSerial.printf("Displayed page %d (%s)\n", page, PAGE_NAMES[page]);
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
  } while (display.nextPage());
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
  } while (display.nextPage());
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
  } while (display.nextPage());
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
  } while (display.nextPage());
}

void clearStoredPage(int page) {
  if (!isValidPageIndex(page)) {
    return;
  }
  if (pageStorage[page] != nullptr) {
    memset(pageStorage[page], 0xFF, IMAGE_BYTES);
  }
  pageLoaded[page] = false;
}

void appendCapabilityFields(JsonDocument& doc) {
  doc["hostname"] = HOSTNAME;
  doc["firmware_version"] = FIRMWARE_VERSION;
  doc["build_sha"] = BUILD_SHA;
  doc["build_time"] = BUILD_TIME;
  doc["width"] = DISPLAY_WIDTH;
  doc["height"] = DISPLAY_HEIGHT;
  doc["image_bytes"] = IMAGE_BYTES;
  doc["page_slots"] = NUM_PAGES;
  doc["snapshot_readback"] = true;
  doc["current_page"] = currentPage;
  doc["current_page_name"] = PAGE_NAMES[currentPage];
  doc["current_page_loaded"] = pageLoaded[currentPage];

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
  String html = "<h1>reTerminal E1001</h1>";
  html += "<p>IP: " + WiFi.localIP().toString() + "</p>";
  html += "<p>Endpoints: /status, /capabilities, /buttons, /beep, /page, /snapshot, /imageraw, /clear</p>";
  server.send(200, "text/html", html);
}

void handleStatus() {
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
  beep(300);
  server.send(200, "application/json", "{\"beeped\": true}");
}

void handlePage() {
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

  beep(100);
  showPage(currentPage);

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

    memcpy(pageStorage[uploadTargetPage], imageBuffer, IMAGE_BYTES);
    pageLoaded[uploadTargetPage] = true;

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
  } while (display.nextPage());

  server.send(200, "application/json", "{\"success\": true, \"displayed\": true}");
  resetUploadState();
}

void handleClear() {
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
  server.send(404, "application/json", "{\"error\": \"Not Found\"}");
}

void setup() {
  // USB Serial on GPIO 44/43 (per working example)
  usbSerial.begin(115200, SERIAL_8N1, 44, 43);
  delay(500);
  usbSerial.println("\n\nreTerminal E1001 Starting...");

  // Buttons
  pinMode(BTN_LEFT, INPUT_PULLUP);
  pinMode(BTN_MIDDLE, INPUT_PULLUP);
  pinMode(BTN_RIGHT, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Read initial button states
  lastLeft = digitalRead(BTN_LEFT);
  lastMiddle = digitalRead(BTN_MIDDLE);
  lastRight = digitalRead(BTN_RIGHT);

  // Allocate page storage in PSRAM
  usbSerial.println("Allocating page storage...");
  for (int i = 0; i < NUM_PAGES; i++) {
    pageStorage[i] = (uint8_t*)ps_malloc(IMAGE_BYTES);
    if (pageStorage[i] == nullptr) {
      pageStorage[i] = (uint8_t*)malloc(IMAGE_BYTES);
    }
    if (pageStorage[i] != nullptr) {
      memset(pageStorage[i], 0xFF, IMAGE_BYTES);
      usbSerial.printf("  Page %d: OK\n", i);
    } else {
      usbSerial.printf("  Page %d: FAILED\n", i);
    }
  }

  // Initialize display SPI
  hspi.begin(EPD_SCK_PIN, -1, EPD_MOSI_PIN, -1);
  display.epd2.selectSPI(hspi, SPISettings(2000000, MSBFIRST, SPI_MODE0));
  display.init(115200, true);
  display.setRotation(0);
  usbSerial.println("Display initialized");

  // Show boot screen
  showBootScreen();

  // Connect WiFi
  if (strlen(WIFI_SSID) > 0) {
    WiFi.setHostname(HOSTNAME);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    usbSerial.print("Connecting to WiFi");

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
      delay(500);
      usbSerial.print(".");
      attempts++;
    }
    usbSerial.println();

    if (WiFi.status() == WL_CONNECTED) {
      usbSerial.println("Connected! IP: " + WiFi.localIP().toString());
      showReadyScreen(WiFi.localIP().toString());
      beep(100);
    } else {
      usbSerial.println("WiFi failed!");
      showConfigRequiredScreen("WiFi connect failed", "Check platformio.local.ini");
    }
  } else {
    usbSerial.println("WiFi credentials not configured");
    showConfigRequiredScreen("WiFi not configured", "Set platformio.local.ini");
  }

  // HTTP routes
  server.on("/", handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/capabilities", HTTP_GET, handleCapabilities);
  server.on("/snapshot", HTTP_GET, handleSnapshot);
  server.on("/buttons", HTTP_GET, handleButtons);
  server.on("/beep", HTTP_GET, handleBeep);
  server.on("/page", handlePage);
  server.on("/imageraw", HTTP_POST, handleImageRaw, handleImageUpload);
  server.on("/clear", HTTP_POST, handleClear);
  server.onNotFound(handleNotFound);
  server.begin();
  usbSerial.println("HTTP server started");

  // OTA
  if (WiFi.status() == WL_CONNECTED && strlen(OTA_PASSWORD) > 0) {
    ArduinoOTA.setHostname(HOSTNAME);
    ArduinoOTA.setPassword(OTA_PASSWORD);
    ArduinoOTA.onStart([]() { usbSerial.println("OTA starting..."); });
    ArduinoOTA.onEnd([]() { usbSerial.println("OTA done!"); });
    ArduinoOTA.begin();
    usbSerial.println("OTA ready");
  } else {
    usbSerial.println("OTA disabled (set RETERMINAL_OTA_PASSWORD to enable)");
  }

  usbSerial.println("Setup complete!");
}

void loop() {
  ArduinoOTA.handle();
  server.handleClient();

  // Check buttons (same pattern as working example)
  bool curLeft = digitalRead(BTN_LEFT);
  if (curLeft != lastLeft) {
    delay(DEBOUNCE_MS);
    if (curLeft == LOW) {
      usbSerial.println("Left button - Previous page");
      beep(100);
      currentPage = (currentPage - 1 + NUM_PAGES) % NUM_PAGES;
      showPage(currentPage);
    }
    lastLeft = curLeft;
  }

  bool curMiddle = digitalRead(BTN_MIDDLE);
  if (curMiddle != lastMiddle) {
    delay(DEBOUNCE_MS);
    if (curMiddle == LOW) {
      usbSerial.println("Middle button - Next page");
      beep(100);
      currentPage = (currentPage + 1) % NUM_PAGES;
      showPage(currentPage);
    }
    lastMiddle = curMiddle;
  }

  bool curRight = digitalRead(BTN_RIGHT);
  if (curRight != lastRight) {
    delay(DEBOUNCE_MS);
    if (curRight == LOW) {
      usbSerial.println("Right button - Refresh");
      beep(100);
      showPage(currentPage);
    }
    lastRight = curRight;
  }

  delay(10);
}
