/*
 * reTerminal E1001 HTTP API Firmware
 * Based on Handy4ndy's working GxEPD2 examples
 *
 * Endpoints:
 *   GET  /status     - Device status
 *   GET  /buttons    - Button states
 *   GET  /beep       - Test buzzer
 *   POST /page       - Set/get current page
 *   POST /imageraw   - Upload raw 1-bit image (800x480, 48000 bytes)
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ArduinoOTA.h>
#include <ArduinoJson.h>
#include <GxEPD2_BW.h>
#include <Fonts/FreeMonoBold18pt7b.h>

// WiFi credentials
const char* WIFI_SSID = "HORUS";
const char* WIFI_PASS = "homesweethome";
const char* HOSTNAME = "reterminal";

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
const char* PAGE_NAMES[] = {"dashboard", "clock", "github", "quote"};
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

    // Page indicator at bottom
    display.setFont(&FreeMonoBold18pt7b);
    display.setTextColor(GxEPD_BLACK);
    String pageText = "Page " + String(page + 1) + "/" + String(NUM_PAGES);
    printCentered(pageText.c_str(), 440);

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

// === HTTP Handlers ===

void handleRoot() {
  String html = "<h1>reTerminal E1001</h1>";
  html += "<p>IP: " + WiFi.localIP().toString() + "</p>";
  html += "<p>Endpoints: /status, /buttons, /beep, /page, /imageraw</p>";
  server.send(200, "text/html", html);
}

void handleStatus() {
  JsonDocument doc;
  doc["ip"] = WiFi.localIP().toString();
  doc["rssi"] = WiFi.RSSI();
  doc["ssid"] = WiFi.SSID();
  doc["uptime_ms"] = millis();
  doc["free_heap"] = ESP.getFreeHeap();
  doc["current_page"] = currentPage;
  doc["page_name"] = PAGE_NAMES[currentPage];

  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
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
  } else if (server.method() == HTTP_POST) {
    String body = server.arg("plain");
    JsonDocument doc;
    if (deserializeJson(doc, body) == DeserializationError::Ok) {
      if (doc["page"].is<int>()) {
        currentPage = doc["page"].as<int>() % NUM_PAGES;
        beep(100);
        showPage(currentPage);
      } else if (doc["action"].is<const char*>()) {
        const char* action = doc["action"];
        if (strcmp(action, "next") == 0) {
          currentPage = (currentPage + 1) % NUM_PAGES;
        } else if (strcmp(action, "prev") == 0) {
          currentPage = (currentPage - 1 + NUM_PAGES) % NUM_PAGES;
        }
        beep(100);
        showPage(currentPage);
      }
    }
    JsonDocument resp;
    resp["page"] = currentPage;
    resp["name"] = PAGE_NAMES[currentPage];
    String response;
    serializeJson(resp, response);
    server.send(200, "application/json", response);
  }
}

// Upload state for chunked image uploads
size_t uploadBytesReceived = 0;
int uploadTargetPage = -1;

void handleImageUpload() {
  HTTPUpload& upload = server.upload();

  if (upload.status == UPLOAD_FILE_START) {
    uploadBytesReceived = 0;
    uploadTargetPage = -1;

    String pageArg = server.arg("page");
    if (pageArg.length() > 0) {
      uploadTargetPage = pageArg.toInt();
      if (uploadTargetPage < 0 || uploadTargetPage >= NUM_PAGES) uploadTargetPage = -1;
    }

    // Allocate buffer
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
    server.send(405, "text/plain", "Method Not Allowed");
    return;
  }

  // Check if we got the right amount of data
  if (uploadBytesReceived != IMAGE_BYTES) {
    server.send(400, "application/json",
      "{\"error\": \"Invalid size\", \"expected\": " + String(IMAGE_BYTES) +
      ", \"received\": " + String(uploadBytesReceived) + "}");
    return;
  }

  if (imageBuffer == nullptr) {
    server.send(500, "application/json", "{\"error\": \"No buffer\"}");
    return;
  }

  // Store to page or display immediately
  if (uploadTargetPage >= 0 && pageStorage[uploadTargetPage] != nullptr) {
    memcpy(pageStorage[uploadTargetPage], imageBuffer, IMAGE_BYTES);
    pageLoaded[uploadTargetPage] = true;

    if (uploadTargetPage == currentPage) {
      showPage(currentPage);
    }

    server.send(200, "application/json",
      "{\"success\": true, \"page\": " + String(uploadTargetPage) + "}");
  } else {
    // Display immediately
    display.setFullWindow();
    display.firstPage();
    do {
      display.fillScreen(GxEPD_WHITE);
      display.drawBitmap(0, 0, imageBuffer, DISPLAY_WIDTH, DISPLAY_HEIGHT, GxEPD_BLACK);
    } while (display.nextPage());

    server.send(200, "application/json", "{\"success\": true, \"displayed\": true}");
  }

  uploadBytesReceived = 0;
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
  }

  // HTTP routes
  server.on("/", handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/buttons", HTTP_GET, handleButtons);
  server.on("/beep", HTTP_GET, handleBeep);
  server.on("/page", handlePage);
  server.on("/imageraw", HTTP_POST, handleImageRaw, handleImageUpload);
  server.onNotFound(handleNotFound);
  server.begin();
  usbSerial.println("HTTP server started");

  // OTA
  ArduinoOTA.setHostname(HOSTNAME);
  ArduinoOTA.onStart([]() { usbSerial.println("OTA starting..."); });
  ArduinoOTA.onEnd([]() { usbSerial.println("OTA done!"); });
  ArduinoOTA.begin();
  usbSerial.println("OTA ready");

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
