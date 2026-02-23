/*
 ╔══════════════════════════════════════════════════════════════════════════════╗
 ║   ESP32-CAM AI TRAFFIC LIVE — FIRMWARE v3.0                                  ║
 ║   Board: ESP32-CAM (AI Thinker) — Sensor: OV2640 / OV5640                    ║
 ║   USB-UART: FT231 / CP2102                                                   ║
 ║                                                                              ║
 ║   CAMERA MODE LOGIC:                                                         ║
 ║     GREEN  → IDLE   (không chụp)                                             ║
 ║     YELLOW → WARMUP (kích hoạt, chờ)                                         ║
 ║     RED    → ACTIVE (chụp 500ms/frame, phát hiện vi phạm)                    ║
 ║                                                                              ║
 ║   CAMERA SETTINGS (OCR-optimized):                                           ║
 ║     Frame:   XGA 1024×768  (OCR biển số chuẩn)                               ║
 ║     Quality: 8             (JPEG — tốt nhất cho OCR)                         ║
 ║     FBuf:    2             (ổn định + ít RAM)                                ║
 ║     AE lvl: -2             (sáng vừa)                                        ║
 ║     Gain:   4X             (ít nhiễu)                                        ║
 ║                                                                              ║
 ║   MQTT TOPICS:                                                               ║
 ║     PUB → traffic/esp32/status    (heartbeat, telemetry)                     ║
 ║     PUB → traffic/esp32/frame     (JPEG base64 frames)                       ║
 ║     PUB → traffic/ai/context      (speed, weather, vehicles...)              ║
 ║     PUB → traffic/light/state     (light sync to server)                     ║
 ║     SUB → traffic/cmd/light       (force light from server)                  ║
 ║     SUB → traffic/cmd/emergency   (emergency mode)                           ║
 ╚══════════════════════════════════════════════════════════════════════════════╝
*/

// ============================================================================
// LIBRARIES
// ============================================================================

#include "esp_camera.h"
#include "esp_timer.h"
#include "img_converters.h"

#include <WiFi.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <base64.h>

// ============================================================================
// ─── PIN MAP — AI Thinker ESP32-CAM ─────────────────────────────────────────
// ============================================================================

#define CAM_PIN_PWDN    32
#define CAM_PIN_RESET   -1    // Software reset
#define CAM_PIN_XCLK     0
#define CAM_PIN_SIOD    26
#define CAM_PIN_SIOC    27

#define CAM_PIN_D7      35
#define CAM_PIN_D6      34
#define CAM_PIN_D5      39
#define CAM_PIN_D4      36
#define CAM_PIN_D3      21
#define CAM_PIN_D2      19
#define CAM_PIN_D1      18
#define CAM_PIN_D0       5

#define CAM_PIN_VSYNC   25
#define CAM_PIN_HREF    23
#define CAM_PIN_PCLK    22

// Onboard flash LED (GPIO 4 on AI Thinker)
#define FLASH_LED_PIN    4

// ============================================================================
// ─── WIFI CONFIG ─────────────────────────────────────────────────────────────
// ============================================================================

const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASS     = "YOUR_WIFI_PASSWORD";
const int   WIFI_TIMEOUT  = 20000;   // 20s timeout

// ============================================================================
// ─── MQTT CONFIG ─────────────────────────────────────────────────────────────
// ============================================================================

const char* MQTT_HOST     = "broker.hivemq.com";
const int   MQTT_PORT     = 1883;
const int   MQTT_KEEPALIVE = 60;

// ── Publish topics ──
const char* TOPIC_STATUS   = "traffic/esp32/status";     // Heartbeat
const char* TOPIC_FRAME    = "traffic/esp32/frame";      // JPEG frame (base64)
const char* TOPIC_CONTEXT  = "traffic/ai/context";       // Context telemetry
const char* TOPIC_LIGHT    = "traffic/light/state";      // Light state → server

// ── Subscribe topics ──
const char* TOPIC_CMD_LIGHT  = "traffic/cmd/light";      // Force light
const char* TOPIC_CMD_EMERG  = "traffic/cmd/emergency";  // Emergency mode

// ── MQTT message buffer ──
#define MQTT_MAX_PACKET 20000   // 20KB for base64 XGA frames

// ============================================================================
// ─── DEVICE INFO ─────────────────────────────────────────────────────────────
// ============================================================================

const char* DEVICE_ID   = "ESP32_CAM_01";
const char* FIRMWARE_VER = "3.0.0";

// ============================================================================
// ─── TRAFFIC STATE ───────────────────────────────────────────────────────────
// ============================================================================

enum LightState { LIGHT_GREEN, LIGHT_YELLOW, LIGHT_RED };
enum CameraMode { CAM_IDLE, CAM_WARMUP, CAM_ACTIVE };

struct TrafficState {
  LightState  light        = LIGHT_RED;
  CameraMode  camMode      = CAM_ACTIVE;
  int         countdown    = 30;
  bool        emergencyMode = false;
  bool        serverSync    = false;     // True = server controls cycle
  // Cycle durations (seconds)
  int         greenDur      = 30;
  int         yellowDur     = 5;
  int         redDur        = 30;
};

TrafficState ts;

// ============================================================================
// ─── CONTEXT STATE (7 ESP32 limits) ─────────────────────────────────────────
// ============================================================================

struct ContextState {
  float   speed_kmh        = 0.0;
  int     vehicles_frame   = 0;
  String  weather          = "SUN";     // SUN | LIGHT_RAIN | CLOUDY
  float   distance         = 5.0;
  float   capture_interval = 0.5;       // seconds
  String  roi              = "STOP_LINE";
  float   fps              = 0.0;
  bool    context_ok       = true;
};

ContextState ctx;

// ============================================================================
// ─── CAMERA STATS ────────────────────────────────────────────────────────────
// ============================================================================

struct CameraStats {
  uint32_t framesCaptured  = 0;
  uint32_t framesPublished = 0;
  uint32_t framesFailed    = 0;
  uint32_t captureTimeMs   = 0;   // last capture duration
  float    actualFps       = 0.0;
  bool     initialized     = false;
};

CameraStats camStats;

// ============================================================================
// ─── TIMING ──────────────────────────────────────────────────────────────────
// ============================================================================

unsigned long lastCycleTick     = 0;
unsigned long lastHeartbeat     = 0;
unsigned long lastContextSend   = 0;
unsigned long lastFrameCapture  = 0;
unsigned long lastWifiCheck     = 0;
unsigned long lastFpsCalc       = 0;

uint32_t fpsCounter             = 0;

// ============================================================================
// ─── NETWORK OBJECTS ─────────────────────────────────────────────────────────
// ============================================================================

WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);

// ============================================================================
// ─── HELPERS ─────────────────────────────────────────────────────────────────
// ============================================================================

String lightStateStr(LightState l) {
  switch (l) {
    case LIGHT_GREEN:  return "GREEN";
    case LIGHT_YELLOW: return "YELLOW";
    default:           return "RED";
  }
}

CameraMode cameraModeForLight(LightState l) {
  switch (l) {
    case LIGHT_GREEN:  return CAM_IDLE;
    case LIGHT_YELLOW: return CAM_WARMUP;
    default:           return CAM_ACTIVE;
  }
}

String cameraModeStr(CameraMode m) {
  switch (m) {
    case CAM_IDLE:    return "IDLE";
    case CAM_WARMUP:  return "WARMUP";
    default:          return "ACTIVE";
  }
}

String ipStr() {
  IPAddress ip = WiFi.localIP();
  return String(ip[0]) + "." + String(ip[1]) + "." +
         String(ip[2]) + "." + String(ip[3]);
}

uint32_t nowTs() {
  return (uint32_t)time(NULL);
}

// ============================================================================
// ─── MQTT PUBLISH HELPERS ────────────────────────────────────────────────────
// ============================================================================

bool publishJson(const char* topic, JsonDocument& doc, int qos = 1) {
  if (!mqtt.connected()) return false;
  char buf[1024];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  if (n == 0) return false;
  return mqtt.publish(topic, (const uint8_t*)buf, n, false);
}

bool publishRaw(const char* topic, const uint8_t* data, size_t len, int qos = 0) {
  if (!mqtt.connected()) return false;
  return mqtt.publish(topic, data, len, false);
}

// ============================================================================
// ─── LED 7-SEGMENT DRIVER (mock — replace with hardware SPI/I2C driver) ──────
// ============================================================================

void updateSevenSegment(int val) {
  // TODO: Replace with actual 7-segment display library
  // e.g.: display.showNumberDec(val, false);
  Serial.printf("[SEG] Countdown: %d\n", val);
}

// ============================================================================
// ─── FLASH LED CONTROL ───────────────────────────────────────────────────────
// ============================================================================

void flashOn(int brightness = 128) {
  ledcWrite(LEDC_CHANNEL_1, brightness);
}

void flashOff() {
  ledcWrite(LEDC_CHANNEL_1, 0);
}

// ============================================================================
// ─── CAMERA INITIALIZATION ───────────────────────────────────────────────────
//
//  Two profiles:
//    STREAM  → VGA  640×480  quality=12  fb=3  (fast, 25-30 FPS)
//    OCR     → XGA  1024×768 quality=8   fb=2  (best plate recognition)
//
//  Active profile switches based on camera mode:
//    IDLE/WARMUP → VGA stream (preview)
//    ACTIVE/RED  → XGA OCR   (capture for AI)
// ============================================================================

bool initCamera(bool ocrMode = false) {
  // Power down reset
  if (camStats.initialized) {
    esp_camera_deinit();
    camStats.initialized = false;
    delay(100);
  }

  camera_config_t config;
  config.pin_pwdn     = CAM_PIN_PWDN;
  config.pin_reset    = CAM_PIN_RESET;
  config.pin_xclk     = CAM_PIN_XCLK;
  config.pin_sccb_sda = CAM_PIN_SIOD;
  config.pin_sccb_scl = CAM_PIN_SIOC;
  config.pin_d7       = CAM_PIN_D7;
  config.pin_d6       = CAM_PIN_D6;
  config.pin_d5       = CAM_PIN_D5;
  config.pin_d4       = CAM_PIN_D4;
  config.pin_d3       = CAM_PIN_D3;
  config.pin_d2       = CAM_PIN_D2;
  config.pin_d1       = CAM_PIN_D1;
  config.pin_d0       = CAM_PIN_D0;
  config.pin_vsync    = CAM_PIN_VSYNC;
  config.pin_href     = CAM_PIN_HREF;
  config.pin_pclk     = CAM_PIN_PCLK;

  config.xclk_freq_hz = 20000000;          // 20 MHz — maximum stable
  config.ledc_timer   = LEDC_TIMER_0;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.pixel_format = PIXFORMAT_JPEG;

  // ── PSRAM detection ──
  bool hasPSRAM = psramFound();

  if (ocrMode && hasPSRAM) {
    // ─── OCR MODE — XGA 1024×768 ─────────────────────────────────────────
    // Best plate recognition quality
    // Ref: FRAMESIZE_XGA = 1024x768
    config.frame_size   = FRAMESIZE_XGA;
    config.jpeg_quality = 8;              // 8-10: best OCR quality
    config.fb_count     = 2;              // 2: stable with XGA
    config.grab_mode    = CAMERA_GRAB_LATEST;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
    Serial.println("[CAM] 📷 OCR Mode: XGA 1024×768 Q=8 FB=2");

  } else {
    // ─── STREAM MODE — VGA 640×480 ───────────────────────────────────────
    // Fast preview / live dashboard stream
    config.frame_size   = FRAMESIZE_VGA;
    config.jpeg_quality = 12;             // 12: fast encoding, 25-30 FPS
    config.fb_count     = hasPSRAM ? 3 : 2;
    config.grab_mode    = CAMERA_GRAB_LATEST;
    config.fb_location  = hasPSRAM ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
    Serial.println("[CAM] 🎥 Stream Mode: VGA 640×480 Q=12 FB=3");
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] ❌ Init failed: 0x%x\n", err);
    return false;
  }

  // ── Sensor tuning ──
  sensor_t* s = esp_camera_sensor_get();
  if (s) {
    if (ocrMode) {
      // OCR-optimized sensor settings
      s->set_quality(s, 8);
      s->set_framesize(s, FRAMESIZE_XGA);
      s->set_ae_level(s, -2);           // Exposure: slightly bright
      s->set_gainceiling(s, GAINCEILING_4X);  // Low noise
      s->set_contrast(s, 1);            // +1 contrast
      s->set_sharpness(s, 2);           // +2 sharpness for plate text
      s->set_denoise(s, 1);             // Denoise on
      s->set_bpc(s, 1);                 // Bad pixel correction
      s->set_wpc(s, 1);                 // White pixel correction
      s->set_awb_gain(s, 1);            // Auto white balance gain
      s->set_whitebal(s, 1);            // AWB on
      s->set_exposure_ctrl(s, 1);       // Auto exposure on
      s->set_aec2(s, 1);                // AEC DSP on
      // Manual exposure hint (300-400 recommended)
      s->set_aec_value(s, 350);
      Serial.println("[CAM] ✅ OCR sensor tuning applied");
    } else {
      // Stream mode — fast settings
      s->set_quality(s, 12);
      s->set_framesize(s, FRAMESIZE_VGA);
      s->set_ae_level(s, 0);
      s->set_gainceiling(s, GAINCEILING_2X);
      s->set_contrast(s, 0);
      s->set_sharpness(s, 0);
      Serial.println("[CAM] ✅ Stream sensor tuning applied");
    }

    // Common settings
    s->set_hmirror(s, 0);       // Horizontal mirror: off
    s->set_vflip(s, 0);         // Vertical flip: off
    s->set_colorbar(s, 0);      // Test pattern: off
  }

  camStats.initialized = true;
  Serial.println("[CAM] ✅ Camera initialized");
  return true;
}

// ============================================================================
// ─── FRAME CAPTURE & PUBLISH ─────────────────────────────────────────────────
// ============================================================================

/*
 * captureAndPublish()
 *
 * Called only when:
 *   1. Camera mode is ACTIVE (RED light)
 *   2. Interval >= capture_interval (default 500ms)
 *
 * Flow:
 *   → Re-init camera in OCR mode (XGA) if needed
 *   → Capture frame
 *   → Base64 encode
 *   → Publish to TOPIC_FRAME via MQTT
 *   → Re-init back to stream mode if transitioning out of RED
 */

bool _inOcrMode = false;

void captureAndPublish() {
  if (!camStats.initialized) return;

  unsigned long t0 = millis();

  // Switch to OCR mode on RED light
  if (!_inOcrMode) {
    Serial.println("[CAM] 🔄 Switching to OCR mode (XGA)...");
    initCamera(true);
    _inOcrMode = true;
    delay(200);   // sensor stabilize
  }

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    camStats.framesFailed++;
    Serial.println("[CAM] ❌ Frame capture failed");
    return;
  }

  camStats.framesCaptured++;
  camStats.captureTimeMs = millis() - t0;

  // ── Validate JPEG ──
  if (fb->format != PIXFORMAT_JPEG || fb->len < 100) {
    Serial.println("[CAM] ⚠️  Invalid JPEG frame — skipping");
    esp_camera_fb_return(fb);
    camStats.framesFailed++;
    return;
  }

  // ── Base64 encode ──
  // MQTT max payload: 20KB — XGA JPEG is typically 30-80KB
  // If > 16KB, downscale by publishing raw JPEG bytes directly (binary)
  
  bool published = false;

  if (fb->len <= 15000) {
    // Small enough for base64 in JSON payload
    String b64 = base64::encode(fb->buf, fb->len);
    StaticJsonDocument<512> meta;
    meta["device_id"]   = DEVICE_ID;
    meta["ts"]          = nowTs();
    meta["width"]       = fb->width;
    meta["height"]      = fb->height;
    meta["size"]        = fb->len;
    meta["capture_ms"]  = camStats.captureTimeMs;
    meta["light"]       = lightStateStr(ts.light);
    // Append base64 as field
    char topic_with_meta[128];
    snprintf(topic_with_meta, sizeof(topic_with_meta), "%s", TOPIC_FRAME);
    published = publishRaw(
      TOPIC_FRAME,
      (const uint8_t*)b64.c_str(),
      b64.length(),
      0    // QoS 0 for video — speed > reliability
    );
  } else {
    // Large frame — publish raw JPEG bytes directly
    published = publishRaw(
      TOPIC_FRAME,
      fb->buf,
      fb->len,
      0
    );
  }

  esp_camera_fb_return(fb);

  if (published) {
    camStats.framesPublished++;
    fpsCounter++;
    Serial.printf("[CAM] ✅ Frame #%lu pub (%lu bytes, %lums)\n",
                  camStats.framesCaptured, (unsigned long)0, camStats.captureTimeMs);
  } else {
    Serial.println("[CAM] ⚠️  Frame publish failed (MQTT buffer?)");
  }
}

/*
 * captureStreamFrame()
 * Lightweight preview frame for IDLE/WARMUP modes (VGA stream)
 */
void captureStreamFrame() {
  if (!camStats.initialized) return;

  // Switch back to stream mode
  if (_inOcrMode) {
    Serial.println("[CAM] 🔄 Switching back to Stream mode (VGA)...");
    initCamera(false);
    _inOcrMode = false;
    return;  // Skip this frame — let camera stabilize
  }

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return;

  if (fb->len > 0 && fb->format == PIXFORMAT_JPEG) {
    publishRaw(TOPIC_FRAME, fb->buf, fb->len, 0);
    fpsCounter++;
  }
  esp_camera_fb_return(fb);
}

// ============================================================================
// ─── MQTT PUBLISH FUNCTIONS ───────────────────────────────────────────────────
// ============================================================================

/* ── Heartbeat / Device Status ── */
void publishHeartbeat() {
  StaticJsonDocument<512> doc;
  doc["device_id"]   = DEVICE_ID;
  doc["fw"]          = FIRMWARE_VER;
  doc["ip"]          = ipStr();
  doc["rssi"]        = WiFi.RSSI();
  doc["ts"]          = nowTs();
  doc["uptime"]      = millis() / 1000;
  doc["heap_free"]   = ESP.getFreeHeap();
  doc["psram_free"]  = psramFound() ? ESP.getFreePsram() : 0;
  doc["cam_ok"]      = camStats.initialized;
  doc["fps"]         = camStats.actualFps;
  doc["frames_pub"]  = camStats.framesPublished;
  doc["cam_mode"]    = cameraModeStr(ts.camMode);
  doc["light"]       = lightStateStr(ts.light);

  publishJson(TOPIC_STATUS, doc, 1);
}

/* ── Context Telemetry (7 ESP32 limit params) ── */
void publishContext() {
  StaticJsonDocument<512> doc;
  doc["device_id"]        = DEVICE_ID;
  doc["speed_kmh"]        = ctx.speed_kmh;
  doc["vehicles_frame"]   = ctx.vehicles_frame;
  doc["weather"]          = ctx.weather;
  doc["distance"]         = ctx.distance;
  doc["capture_interval"] = ctx.capture_interval;
  doc["roi"]              = ctx.roi;
  doc["fps"]              = camStats.actualFps;
  JsonArray objs = doc.createNestedArray("target_objects");
  objs.add("MOTORBIKE");
  objs.add("CAR");
  doc["context_ok"]       = ctx.context_ok;
  doc["ts"]               = nowTs();

  publishJson(TOPIC_CONTEXT, doc, 1);
}

/* ── Traffic Light State ── */
void publishLightState() {
  StaticJsonDocument<256> doc;
  doc["device_id"] = DEVICE_ID;
  doc["light"]     = lightStateStr(ts.light);
  doc["countdown"] = ts.countdown;
  doc["camera"]    = cameraModeStr(ts.camMode);
  doc["mode"]      = ts.emergencyMode ? "EMERGENCY" : (ts.serverSync ? "SERVER_SYNC" : "AUTO");
  doc["ts"]        = nowTs();

  publishJson(TOPIC_LIGHT, doc, 1);
}

// ============================================================================
// ─── TRAFFIC CYCLE ───────────────────────────────────────────────────────────
// ============================================================================

/*
 * advanceLightCycle()
 * Called every 1 second. Manages GREEN → YELLOW → RED transitions.
 * Camera mode automatically follows light state.
 *
 * Camera trigger logic:
 *   YELLOW (last 2-3s) → Warmup camera
 *   RED                → ACTIVE capture at 500ms intervals
 *   GREEN              → IDLE, stop capture
 */
void advanceLightCycle() {
  ts.countdown--;

  if (ts.countdown <= 0) {
    switch (ts.light) {
      case LIGHT_GREEN:
        ts.light     = LIGHT_YELLOW;
        ts.countdown = ts.yellowDur;
        Serial.println("[LIGHT] 🟡 GREEN → YELLOW");
        break;
      case LIGHT_YELLOW:
        ts.light     = LIGHT_RED;
        ts.countdown = ts.redDur;
        Serial.println("[LIGHT] 🔴 YELLOW → RED — Camera ACTIVE");
        break;
      case LIGHT_RED:
        ts.light     = LIGHT_GREEN;
        ts.countdown = ts.greenDur;
        Serial.println("[LIGHT] 🟢 RED → GREEN — Camera IDLE");
        break;
    }
    ts.camMode = cameraModeForLight(ts.light);
  }

  // Warmup trigger: last 3 seconds of YELLOW
  if (ts.light == LIGHT_YELLOW && ts.countdown <= 3 && ts.camMode == CAM_WARMUP) {
    Serial.println("[CAM] ⚡ Pre-warmup for RED phase...");
  }

  updateSevenSegment(ts.countdown);
  publishLightState();
}

// ============================================================================
// ─── MQTT MESSAGE HANDLER ────────────────────────────────────────────────────
// ============================================================================

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  String topicStr(topic);
  Serial.printf("[MQTT] ← %s (%u bytes)\n", topic, length);

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) {
    Serial.printf("[MQTT] ❌ JSON parse error: %s\n", err.c_str());
    return;
  }

  // ── Force light command from server/dashboard ──
  if (topicStr == TOPIC_CMD_LIGHT) {
    String light = doc["light"] | "RED";
    String mode  = doc["mode"]  | "EMERGENCY";

    if (light == "GREEN") {
      ts.light     = LIGHT_GREEN;
      ts.countdown = ts.greenDur;
    } else if (light == "YELLOW") {
      ts.light     = LIGHT_YELLOW;
      ts.countdown = ts.yellowDur;
    } else {
      ts.light     = LIGHT_RED;
      ts.countdown = ts.redDur;
    }

    ts.camMode      = cameraModeForLight(ts.light);
    ts.serverSync   = (mode != "AUTO");
    ts.emergencyMode = (mode == "EMERGENCY");

    Serial.printf("[LIGHT] 📡 Server CMD → %s [%s]\n", light.c_str(), mode.c_str());
    publishLightState();
  }

  // ── Emergency command ──
  if (topicStr == TOPIC_CMD_EMERG) {
    bool active = doc["active"] | false;
    String light = doc["light"] | "RED";

    if (active) {
      ts.emergencyMode = true;
      ts.serverSync    = true;
      ts.light         = (light == "GREEN") ? LIGHT_GREEN :
                         (light == "YELLOW") ? LIGHT_YELLOW : LIGHT_RED;
      ts.camMode       = cameraModeForLight(ts.light);
      ts.countdown     = ts.redDur;
      Serial.printf("[EMERGENCY] ⚡ Active → %s\n", light.c_str());

      // Flash LED to indicate emergency
      flashOn(255);
      delay(200);
      flashOff();
    } else {
      ts.emergencyMode = false;
      ts.serverSync    = false;
      Serial.println("[EMERGENCY] ✅ Cleared — returning to AUTO");
    }
    publishLightState();
  }
}

// ============================================================================
// ─── WIFI MANAGEMENT ─────────────────────────────────────────────────────────
// ============================================================================

bool connectWiFi() {
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);            // Disable power save — better latency
  WiFi.setTxPower(WIFI_POWER_19_5dBm); // Max TX power

  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > WIFI_TIMEOUT) {
      Serial.println("\n[WiFi] ❌ Timeout");
      return false;
    }
    delay(250);
    Serial.print(".");
  }

  Serial.printf("\n[WiFi] ✅ Connected: %s RSSI=%ddBm\n",
                ipStr().c_str(), WiFi.RSSI());

  // NTP time sync
  configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");
  delay(1000);
  return true;
}

void checkWiFiReconnect() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] ⚠️  Disconnected — reconnecting...");
    WiFi.disconnect();
    delay(500);
    connectWiFi();
  }
}

// ============================================================================
// ─── MQTT MANAGEMENT ─────────────────────────────────────────────────────────
// ============================================================================

bool mqttConnect() {
  String clientId = String(DEVICE_ID) + "_" + String(random(0xffff), HEX);

  Serial.printf("[MQTT] Connecting %s → %s:%d\n", clientId.c_str(), MQTT_HOST, MQTT_PORT);

  // Last Will Testament — mark device offline on unexpected disconnect
  StaticJsonDocument<128> lwt;
  lwt["device_id"] = DEVICE_ID;
  lwt["online"]    = false;
  lwt["ts"]        = nowTs();
  char lwtBuf[128];
  serializeJson(lwt, lwtBuf, sizeof(lwtBuf));

  bool ok = mqtt.connect(
    clientId.c_str(),
    nullptr, nullptr,   // no auth
    TOPIC_STATUS,       // LWT topic
    1,                  // LWT QoS
    true,               // LWT retain
    lwtBuf              // LWT payload
  );

  if (!ok) {
    Serial.printf("[MQTT] ❌ Connect failed: rc=%d\n", mqtt.state());
    return false;
  }

  Serial.println("[MQTT] ✅ Connected");

  // Subscribe
  mqtt.subscribe(TOPIC_CMD_LIGHT, 1);
  mqtt.subscribe(TOPIC_CMD_EMERG, 1);

  // Publish online status immediately
  publishHeartbeat();
  publishLightState();

  return true;
}

void checkMqttReconnect() {
  static unsigned long lastAttempt = 0;
  if (!mqtt.connected() && millis() - lastAttempt > 5000) {
    lastAttempt = millis();
    if (!mqttConnect()) {
      Serial.println("[MQTT] ⏳ Retry in 5s...");
    }
  }
}

// ============================================================================
// ─── FPS CALCULATOR ──────────────────────────────────────────────────────────
// ============================================================================

void calcFps() {
  unsigned long now = millis();
  if (now - lastFpsCalc >= 1000) {
    camStats.actualFps = (float)fpsCounter / ((now - lastFpsCalc) / 1000.0f);
    ctx.fps            = camStats.actualFps;
    fpsCounter         = 0;
    lastFpsCalc        = now;
  }
}

// ============================================================================
// ─── CONTEXT SIMULATION ──────────────────────────────────────────────────────
// (Replace with real sensor readings when hardware available)
// ============================================================================

void updateContextFromSensors() {
  // TODO: Replace with real sensor data
  // Speed: Ultrasonic HC-SR04 or IR sensor array
  // Weather: DHT22 / light sensor / rain sensor
  // Distance: calibrated from camera mount height

  ctx.speed_kmh        = (float)(random(5, 22));      // 5–22 km/h mock
  ctx.vehicles_frame   = random(0, 7);                // 0–6 vehicles
  ctx.weather          = "SUN";                       // TODO: real sensor
  ctx.distance         = 5.0;                         // Fixed mount
  ctx.capture_interval = 0.5;                         // 500ms
  ctx.roi              = "STOP_LINE";

  // Validate context limits
  ctx.context_ok = (
    ctx.speed_kmh        < 20.0 &&
    ctx.vehicles_frame   <= 6   &&
    ctx.weather          == "SUN" || ctx.weather == "LIGHT_RAIN" || ctx.weather == "CLOUDY" &&
    ctx.capture_interval <= 0.5  &&
    ctx.roi              == "STOP_LINE"
  );

  if (!ctx.context_ok) {
    Serial.println("[CTX] ⚠️  Context limit exceeded!");
  }
}

// ============================================================================
// ─── SETUP ───────────────────────────────────────────────────────────────────
// ============================================================================

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n╔════════════════════════════════════╗");
  Serial.println("║  ESP32-CAM Traffic AI v3.0          ║");
  Serial.println("║  FT231/CP2102 USB-UART Bridge       ║");
  Serial.println("╚════════════════════════════════════╝");

  // Flash LED setup (PWM)
  ledcSetup(LEDC_CHANNEL_1, 5000, 8);
  ledcAttachPin(FLASH_LED_PIN, LEDC_CHANNEL_1);
  flashOff();

  // Init camera in stream mode first
  if (!initCamera(false)) {
    Serial.println("[SETUP] ❌ Camera init failed — halting");
    while (1) { delay(1000); }
  }

  // WiFi
  if (!connectWiFi()) {
    Serial.println("[SETUP] ⚠️  WiFi failed — running offline");
  }

  // MQTT
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqtt.setBufferSize(MQTT_MAX_PACKET);
  mqtt.setKeepAlive(MQTT_KEEPALIVE);

  if (WiFi.isConnected()) {
    mqttConnect();
  }

  // Initial traffic state: start on RED phase
  ts.light     = LIGHT_RED;
  ts.camMode   = CAM_ACTIVE;
  ts.countdown = ts.redDur;

  updateSevenSegment(ts.countdown);

  // Init timing
  lastCycleTick    = millis();
  lastHeartbeat    = millis();
  lastContextSend  = millis();
  lastFrameCapture = millis();
  lastFpsCalc      = millis();

  Serial.println("[SETUP] ✅ System ready");
  Serial.printf("[SETUP] 🔴 Starting on RED — Camera ACTIVE\n");
}

// ============================================================================
// ─── LOOP ────────────────────────────────────────────────────────────────────
// ============================================================================

void loop() {
  unsigned long now = millis();

  // ── Network maintenance ──
  if (now - lastWifiCheck > 30000) {
    lastWifiCheck = now;
    checkWiFiReconnect();
  }
  checkMqttReconnect();
  mqtt.loop();

  // ── FPS calculation ──
  calcFps();

  // ── Traffic cycle tick (every 1s) ──
  if (now - lastCycleTick >= 1000) {
    lastCycleTick = now;

    // Only auto-cycle when not in server/emergency mode
    if (!ts.emergencyMode && !ts.serverSync) {
      advanceLightCycle();
    }

    updateContextFromSensors();
  }

  // ── Camera capture ──
  unsigned long captureIntervalMs = (unsigned long)(ctx.capture_interval * 1000.0f);

  if (now - lastFrameCapture >= captureIntervalMs) {
    lastFrameCapture = now;

    switch (ts.camMode) {
      case CAM_ACTIVE:
        // RED light — full OCR capture
        captureAndPublish();
        break;

      case CAM_WARMUP:
        // YELLOW light — preview stream (no OCR)
        captureStreamFrame();
        break;

      case CAM_IDLE:
        // GREEN light — optional slow stream (1fps preview)
        if (now % 1000 < captureIntervalMs) {
          captureStreamFrame();
        }
        break;
    }
  }

  // ── Heartbeat (every 5s) ──
  if (now - lastHeartbeat >= 5000) {
    lastHeartbeat = now;
    if (mqtt.connected()) {
      publishHeartbeat();
    }
  }

  // ── Context telemetry (every 5s) ──
  if (now - lastContextSend >= 5000) {
    lastContextSend = now;
    if (mqtt.connected()) {
      publishContext();
    }
  }

  // Short yield for watchdog
  delay(1);
}

// ============================================================================
// END OF FILE
// ============================================================================