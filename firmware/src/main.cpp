// Forecast screens (home, boat, chalet, mountain) rendered hourly by render.py and
// published on GitHub Pages as 4-bit frame buffers.
//
// Board: LilyGO T5 4.7" e-paper V2.3 (ESP32-S3-WROOM-1 N16R8), library
// LilyGo-EPD47 (branch esp32s3); build settings in platformio.ini.
//
// Power on, reset, or the hourly timer: download all four screens into
//   flash (LittleFS), full refresh with the current one, deep sleep until
//   HH:FETCH_MINUTE. Failed downloads keep the previous copy; retry after
//   RETRY_S.
// Button (BUTTON_1, GPIO21): wake and show the next screen from flash (no
//   Wi-Fi). It then stays awake AWAKE_MS after the last press (also after
//   power on / reset) so further presses keep switching screens. The chosen
//   screen is kept across resets.

#include <Arduino.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <driver/rtc_io.h>
#include <esp_timer.h>
#include <rom/rtc.h>
#include <time.h>

#include <atomic>

#include "epd_driver.h"
#include "utilities.h"
#include "secrets.h"  // WIFI_SSID, WIFI_PASSWORD, BASE_URL (copy secrets.h.example)

const char *VIEWS[] = {"home", "boat", "chalet", "mountain"};
const int N_VIEWS = sizeof(VIEWS) / sizeof(VIEWS[0]);
const int FETCH_MINUTE = 40;  // render job runs at :12 and :32, GitHub may delay it
const int RETRY_S = 10 * 60;
const uint32_t AWAKE_MS = 20000;  // stay awake after the last button press
// Black/white clear cycles before drawing: full on the hourly update (nobody
// watching, removes any ghosting), light when switching screens by button.
const int FULL_CLEAR_CYCLES = 4;
#ifndef LIGHT_CLEAR_CYCLES
#define LIGHT_CLEAR_CYCLES 1  // set in platformio.ini
#endif
const size_t FB_SIZE = EPD_WIDTH * EPD_HEIGHT / 2;  // 960×540, 4 bits per pixel

static uint8_t *fb;
static std::atomic<uint32_t> presses{0};  // added by the button timer task

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

// Milliseconds since boot, to see where the time goes.
// The last step is also kept in RTC memory, which survives a brownout reset
// (not a power loss), so the next boot can tell where the previous one died.
RTC_NOINIT_ATTR static char last_step[48];
RTC_NOINIT_ATTR static uint32_t last_step_magic;
const uint32_t STEP_MAGIC = 0x57e95afe;

static void stamp(const char *what) {
  snprintf(last_step, sizeof(last_step), "%lu ms %s", millis(), what);
  last_step_magic = STEP_MAGIC;
  Serial.printf("%6lu ms  %s\n", millis(), what);
}

// Full refresh every time (no partial updates, which LilyGO warns leave
// ghosting): clear by flashing black/white `clear_cycles` times, then draw.
// The driver's epd_clear() does 4 cycles (~1.2 s); fewer flash less but may
// leave faint traces of the previous screen.
static void draw(int clear_cycles) {
  epd_poweron();
  stamp("panel powered on");
  epd_clear_area_cycles(epd_full_screen(), clear_cycles, 50);
  stamp(clear_cycles == FULL_CLEAR_CYCLES ? "cleared (full)" : "cleared (light)");
  epd_draw_grayscale_image(epd_full_screen(), fb);
  epd_poweroff();
  stamp("drawn");
}

// Called every 10 ms by an esp_timer, which keeps running during a refresh.
// The button changes state only after reading the same for 30 ms, so contact
// bounce never counts twice; a press counts on the change to down. It starts
// as down, so the press that woke the board counts only once it is released
// and pressed again.
static void sample_button(void *) {
  static bool down = true;
  static uint8_t same = 0;
  bool low = digitalRead(BUTTON_1) == LOW;
  if (low == down) {
    same = 0;
  } else if (++same >= 3) {
    same = 0;
    down = low;
    if (down) presses++;
  }
}

// Keep switching screens on button presses (also those made during a
// refresh) until AWAKE_MS without one. Returns the screen shown last.
static int switch_screens(int view) {
  rtc_gpio_deinit((gpio_num_t)BUTTON_1);  // back to a normal GPIO after ext0 wake
  pinMode(BUTTON_1, INPUT_PULLUP);
  presses = 0;
  esp_timer_create_args_t args = {};
  args.callback = sample_button;
  args.name = "button";
  esp_timer_handle_t timer;
  esp_timer_create(&args, &timer);
  esp_timer_start_periodic(timer, 10 * 1000);
  for (uint32_t last = millis(); millis() - last < AWAKE_MS; delay(20)) {
    uint32_t n = presses.exchange(0);
    if (n) {
      view = (view + n) % N_VIEWS;
      Serial.printf("button: %s\n", VIEWS[view]);
      if (load(VIEWS[view])) draw(LIGHT_CLEAR_CYCLES);
      last = millis();
    }
  }
  esp_timer_stop(timer);
  esp_timer_delete(timer);
  return view;
}

// The panel's power rails (boost converter, +/- high voltage) are switched by
// a 74HCT4094 shift register: data GPIO13, clock GPIO12, strobe GPIO0. The
// strobe idles high (boot pin pull-up), which makes the outputs follow the
// shift register, so an edge on the clock pin while the chip sleeps or wakes
// shifts junk onto the power controls. Hold the pins through deep sleep,
// and at boot close the latch (strobe low) before touching clock and data.
static const gpio_num_t CFG_STR_PIN = GPIO_NUM_0, CFG_CLK_PIN = GPIO_NUM_12,
                        CFG_DATA_PIN = GPIO_NUM_13;

static void hold_cfg_pins() {
  gpio_hold_en(CFG_STR_PIN);
  gpio_hold_en(CFG_CLK_PIN);
  gpio_hold_en(CFG_DATA_PIN);
  gpio_deep_sleep_hold_en();
}

static void release_cfg_pins() {
  gpio_set_level(CFG_STR_PIN, 0);
  gpio_set_direction(CFG_STR_PIN, GPIO_MODE_OUTPUT);
  gpio_hold_dis(CFG_STR_PIN);  // latch closed: clock edges no longer reach the outputs
  gpio_set_level(CFG_CLK_PIN, 1);
  gpio_set_level(CFG_DATA_PIN, 0);
  gpio_set_direction(CFG_CLK_PIN, GPIO_MODE_OUTPUT);
  gpio_set_direction(CFG_DATA_PIN, GPIO_MODE_OUTPUT);
  gpio_hold_dis(CFG_CLK_PIN);
  gpio_hold_dis(CFG_DATA_PIN);
  gpio_deep_sleep_hold_dis();
}

// Bring the power-control register from its sleep state (all 0, left by
// epd_poweroff_all) to the state epd_init sets, one output at a time with
// 20 ms between steps, so epd_init then changes nothing. Switched all at once
// by epd_init, the change browned out the board on about 1 button wake in 4;
// stepped, 0 in 12 (tested 25 Oct 2026). Bit order as in the driver's push_cfg.
static void step_power_controls() {
  enum { OE, MODE, SCAN, STV, NEG, POS, PWR_DISABLE, LE };
  bool cfg[8] = {};
  auto push = [&]() {
    gpio_set_level(CFG_STR_PIN, 0);
    for (bool b : cfg) {
      gpio_set_level(CFG_CLK_PIN, 0);
      gpio_set_level(CFG_DATA_PIN, b);
      gpio_set_level(CFG_CLK_PIN, 1);
    }
    gpio_set_level(CFG_STR_PIN, 1);
    delay(20);
  };
  push();
  for (int bit : {STV, SCAN, PWR_DISABLE}) {
    cfg[bit] = true;
    push();
  }
}

// Seconds until the next HH:FETCH_MINUTE, from the clock set by NTP (it keeps
// running in deep sleep). Swiss time is a whole number of hours from UTC.
// A negative `min_wait` means "if HH:FETCH_MINUTE passed less than that
// long ago, fetch now" (after the button window ran past it).
static uint32_t seconds_to_next_fetch(int min_wait) {
  time_t now = time(nullptr);
  if (now < 1700000000) return 3600;  // clock never set
  struct tm t;
  gmtime_r(&now, &t);
  int wait = FETCH_MINUTE * 60 - (t.tm_min * 60 + t.tm_sec);
  while (wait < min_wait) wait += 3600;
  return max(wait, 1);
}

static void sleep_for(uint32_t seconds) {
  pinMode(BUTTON_1, INPUT_PULLUP);
  for (uint32_t t0 = millis(); digitalRead(BUTTON_1) == LOW && millis() - t0 < 5000;) {
    delay(10);  // wait for release, or the press would wake us straight away
  }
  epd_poweroff_all();
  hold_cfg_pins();
  esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_1, 0);
  rtc_gpio_pullup_en((gpio_num_t)BUTTON_1);
  rtc_gpio_pulldown_dis((gpio_num_t)BUTTON_1);
  esp_sleep_enable_timer_wakeup((uint64_t)seconds * 1000000ULL);
  Serial.printf("sleeping %u s\n", seconds);
  stamp("going to sleep");
  Serial.flush();
  esp_deep_sleep_start();
}

void setup() {
  Serial.begin(115200);
  if (last_step_magic == STEP_MAGIC) {
    last_step[sizeof(last_step) - 1] = 0;
    Serial.printf("        previous boot's last step: %s\n", last_step);
  } else {
    Serial.println("        previous boot's last step: unknown (RTC memory lost)");
  }
  stamp(esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_EXT0    ? "boot: button"
        : esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_TIMER ? "boot: timer"
                                                                 : "boot: power on / reset");
  static const char *REASONS[] = {"unknown", "power on", "external pin", "software", "panic",
                                  "interrupt watchdog", "task watchdog", "other watchdog",
                                  "deep sleep", "brownout", "SDIO"};
  esp_reset_reason_t r = esp_reset_reason();
  // the ROM code tells USB resets apart (21 = USB serial, 22 = USB JTAG)
  Serial.printf("        reset reason: %s (%d), ROM code %d\n", r < 11 ? REASONS[r] : "?", r,
                (int)rtc_get_reset_reason(0));
  fb = (uint8_t *)ps_malloc(FB_SIZE);
  if (!fb || !LittleFS.begin(true)) {
    Serial.println("no PSRAM or flash file system");
    sleep_for(RETRY_S);
  }
  stamp("flash file system mounted");
  release_cfg_pins();
  step_power_controls();
  epd_init();
  stamp("display initialised");

  Preferences prefs;
  prefs.begin("forecast");
  int view = prefs.getInt("view", 0) % N_VIEWS;
  esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
  bool button = cause == ESP_SLEEP_WAKEUP_EXT0;
  if (button) view = (view + 1) % N_VIEWS;

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
  if (load(VIEWS[view])) {
    stamp("screen loaded");
    draw(button ? LIGHT_CLEAR_CYCLES : FULL_CLEAR_CYCLES);
  }
  // someone is at the board (button, power on, reset): give them time to
  // switch screens; the hourly timer goes straight back to sleep
  if (cause != ESP_SLEEP_WAKEUP_TIMER) view = switch_screens(view);
  if (prefs.getInt("view", 0) != view) prefs.putInt("view", view);
  prefs.end();
  sleep_for(ok ? seconds_to_next_fetch(fetch ? 5 * 60 : -(int)(AWAKE_MS / 1000) - 60) : RETRY_S);
}

void loop() {}
