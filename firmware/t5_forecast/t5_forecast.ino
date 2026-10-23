// Forecast screens (home, boat, chalet) rendered hourly by render.py and
// published on GitHub Pages as 4-bit frame buffers.
//
// Board: LilyGO T5 4.7" e-paper V2.3 (ESP32-S3-WROOM-1 N16R8).
// Library: LilyGo-EPD47, branch esp32s3
//   https://github.com/Xinyuan-LilyGO/LilyGo-EPD47/tree/esp32s3
// Arduino IDE: board "ESP32S3 Dev Module", PSRAM "OPI PSRAM",
//   Flash Size "16MB", Partition Scheme with SPIFFS >= 1 MB (the default
//   "Default 4MB with spiffs" has 1.5 MB), USB CDC On Boot "Enabled".
//
// Power on, reset, or the hourly timer: download all three screens into
//   flash (LittleFS), full refresh with the current one, deep sleep until
//   HH:FETCH_MINUTE. Failed downloads keep the previous copy; retry after
//   RETRY_S.
// Button (BUTTON_1, GPIO21): wake, show the next screen from flash (no
//   Wi-Fi), sleep again. The chosen screen is kept across resets.

#include <Arduino.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <driver/rtc_io.h>
#include <time.h>

#include "epd_driver.h"
#include "utilities.h"
#include "secrets.h"  // WIFI_SSID, WIFI_PASSWORD, BASE_URL (copy secrets.h.example)

const char *VIEWS[] = {"home", "boat", "chalet"};
const int N_VIEWS = sizeof(VIEWS) / sizeof(VIEWS[0]);
const int FETCH_MINUTE = 40;  // render job starts at :10, GitHub may delay it
const int RETRY_S = 10 * 60;
const size_t FB_SIZE = EPD_WIDTH * EPD_HEIGHT / 2;  // 960×540, 4 bits per pixel

static uint8_t *fb;

static bool wifi_connect() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  for (uint32_t t0 = millis(); millis() - t0 < 20000; delay(200)) {
    if (WiFi.status() == WL_CONNECTED) return true;
  }
  Serial.println("Wi-Fi: no connection");
  return false;
}

static bool download(const char *view) {
  WiFiClientSecure client;
  client.setInsecure();  // public weather images: no certificate pinning
  HTTPClient http;
  String url = String(BASE_URL) + view + ".raw";
  if (!http.begin(client, url)) return false;
  int code = http.GET();
  int size = http.getSize();  // -1 when the server does not send a length
  size_t got = 0;
  if (code == HTTP_CODE_OK && (size == -1 || size == (int)FB_SIZE)) {
    WiFiClient *s = http.getStreamPtr();
    for (uint32_t t0 = millis(); got < FB_SIZE && millis() - t0 < 30000;) {
      size_t n = s->available();
      if (n) {
        got += s->readBytes(fb + got, min(n, FB_SIZE - got));
      } else if (!http.connected()) {
        break;
      } else {
        delay(5);
      }
    }
  }
  Serial.printf("GET %s: HTTP %d, %u of %u bytes\n", url.c_str(), code, got, FB_SIZE);
  http.end();
  return got == FB_SIZE;
}

static String path(const char *view) { return String("/") + view + ".raw"; }

// Write via a temporary file so a failed write never replaces a good copy.
static bool save(const char *view) {
  File f = LittleFS.open("/tmp.raw", "w");
  if (!f) return false;
  size_t n = f.write(fb, FB_SIZE);
  f.close();
  return n == FB_SIZE && LittleFS.rename("/tmp.raw", path(view));
}

static bool load(const char *view) {
  File f = LittleFS.open(path(view), "r");
  if (!f) return false;
  size_t n = f.read(fb, FB_SIZE);
  f.close();
  return n == FB_SIZE;
}

// Download every screen; returns true if all of them succeeded.
static bool fetch_all() {
  bool all = true;
  for (int i = 0; i < N_VIEWS; i++) {
    all &= download(VIEWS[i]) && save(VIEWS[i]);
  }
  return all;
}

static void draw() {
  epd_poweron();
  epd_clear();  // full refresh every time: no ghosting from partial updates
  epd_draw_grayscale_image(epd_full_screen(), fb);
  epd_poweroff_all();
}

// Seconds until the next HH:FETCH_MINUTE, from the clock set by NTP (it keeps
// running in deep sleep). Swiss time is a whole number of hours from UTC.
static uint32_t seconds_to_next_fetch(int min_wait) {
  time_t now = time(nullptr);
  if (now < 1700000000) return 3600;  // clock never set
  struct tm t;
  gmtime_r(&now, &t);
  int wait = FETCH_MINUTE * 60 - (t.tm_min * 60 + t.tm_sec);
  while (wait < min_wait) wait += 3600;
  return wait;
}

static void sleep_for(uint32_t seconds) {
  pinMode(BUTTON_1, INPUT_PULLUP);
  for (uint32_t t0 = millis(); digitalRead(BUTTON_1) == LOW && millis() - t0 < 5000;) {
    delay(10);  // wait for release, or the press would wake us straight away
  }
  esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_1, 0);
  rtc_gpio_pullup_en((gpio_num_t)BUTTON_1);
  rtc_gpio_pulldown_dis((gpio_num_t)BUTTON_1);
  esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
  Serial.printf("sleeping %u s\n", seconds);
  Serial.flush();
  esp_deep_sleep_start();
}

void setup() {
  Serial.begin(115200);
  fb = (uint8_t *)ps_malloc(FB_SIZE);
  if (!fb || !LittleFS.begin(true)) {
    Serial.println("no PSRAM or flash file system");
    sleep_for(RETRY_S);
  }
  epd_init();

  Preferences prefs;
  prefs.begin("forecast");
  int view = prefs.getInt("view", 0) % N_VIEWS;
  bool button = esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_EXT0;
  if (button) {
    view = (view + 1) % N_VIEWS;
    prefs.putInt("view", view);
  }
  prefs.end();

  // the button only switches screens, unless nothing is stored yet
  bool fetch = !button || !load(VIEWS[view]);
  bool ok = true;
  if (fetch) {
    ok = false;
    if (wifi_connect()) {
      configTime(0, 0, "pool.ntp.org", "time.google.com");
      struct tm t;
      getLocalTime(&t, 10000);
      ok = fetch_all();
    }
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
  }
  if (load(VIEWS[view])) draw();
  sleep_for(ok ? seconds_to_next_fetch(fetch ? 5 * 60 : 1) : RETRY_S);
}

void loop() {}
