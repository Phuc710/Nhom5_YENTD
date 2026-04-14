/*
 * main.cpp — ESP32_PCB: Điều khiển đèn giao thông + Nút bấm + MQTT telemetry.
 *
 * Vai trò: Chỉ điều khiển đèn (không stream camera).
 * - Đèn giao thông 3 màu (Đỏ / Vàng / Xanh) với bộ đếm 7 đoạn
 * - 2 nút bấm vật lý: toggle khẩn cấp đỏ / khẩn cấp xanh
 * - WiFi + MQTT (Mosquitto): publish trạng thái đèn, subscribe lệnh điều khiển
 *
 * MQTT Topics:
 *   Publish : KAI/pcb/{DEVICE_NAME}/telemetry
 *   Subscribe: KAI/pcb/{DEVICE_NAME}/cmd
 *
 * Lệnh cmd nhận (JSON):
 *   {"method":"setNormalMode"}
 *   {"method":"setEmergencyRed"}
 *   {"method":"setEmergencyGreen"}
 *   {"method":"setTimings","params":{"tl_red_ms":5000,"tl_yellow_ms":2000,"tl_green_ms":7000}}
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ─── Compile-time defaults (override qua platformio.ini build_flags) ─────────
#ifndef WIFI_SSID
#  define WIFI_SSID "YourWiFiSSID"
#endif
#ifndef WIFI_PASS
#  define WIFI_PASS "YourWiFiPassword"
#endif
#ifndef MQTT_BROKER_IP
#  define MQTT_BROKER_IP "192.168.1.8"
#endif
#ifndef MQTT_BROKER_PORT
#  define MQTT_BROKER_PORT 1888
#endif
#ifndef DEVICE_NAME
#  define DEVICE_NAME "pcb-tl-01"
#endif

// ─── GPIO đèn giao thông ─────────────────────────────────────────────────────
#ifndef TL_PIN_RED
#  define TL_PIN_RED    21
#endif
#ifndef TL_PIN_YELLOW
#  define TL_PIN_YELLOW 47
#endif
#ifndef TL_PIN_GREEN
#  define TL_PIN_GREEN  14
#endif

// ─── GPIO Shift Register (LED 7 đoạn) ────────────────────────────────────────
#ifndef TL_PIN_SDI
#  define TL_PIN_SDI   38
#endif
#ifndef TL_PIN_SCL
#  define TL_PIN_SCL   39
#endif
#ifndef TL_PIN_KLOAD
#  define TL_PIN_KLOAD 40
#endif

// ─── GPIO Nút bấm (INPUT_PULLUP: LOW = nhấn) ─────────────────────────────────
#ifndef TL_PIN_BTN_RED
#  define TL_PIN_BTN_RED   1
#endif
#ifndef TL_PIN_BTN_GREEN
#  define TL_PIN_BTN_GREEN 2
#endif

// ─── Timing mặc định (ms) ────────────────────────────────────────────────────
#ifndef TL_RED_MS
#  define TL_RED_MS    5000
#endif
#ifndef TL_YELLOW_MS
#  define TL_YELLOW_MS 2000
#endif
#ifndef TL_GREEN_MS
#  define TL_GREEN_MS  7000
#endif

// ─── Cấu hình khác ───────────────────────────────────────────────────────────
#define BTN_DEBOUNCE_MS       50
#define MQTT_RECONNECT_MS   5000
#define TELEMETRY_INTERVAL_MS 1000
#define WIFI_CONNECT_TIMEOUT_MS 20000

// ─── Mã LED 7 đoạn (Anot chung — mức LOW sáng) ───────────────────────────────
static const byte numCode[10] = {
    0xC0, // 0
    0xF9, // 1
    0xA4, // 2
    0xB0, // 3
    0x99, // 4
    0x92, // 5
    0x82, // 6
    0xF8, // 7
    0x80, // 8
    0x90  // 9
};

// ─── Kiểu dữ liệu đèn giao thông ─────────────────────────────────────────────
enum TlState  { TL_RED = 0, TL_YELLOW = 1, TL_GREEN = 2 };
enum TlMode   { TL_NORMAL = 0, TL_EMERGENCY_RED = 1, TL_EMERGENCY_GREEN = 2 };

// ─── Biến toàn cục ───────────────────────────────────────────────────────────
static TlState  g_state      = TL_RED;
static TlMode   g_mode       = TL_NORMAL;
static uint32_t g_red_ms     = TL_RED_MS;
static uint32_t g_yellow_ms  = TL_YELLOW_MS;
static uint32_t g_green_ms   = TL_GREEN_MS;
static uint32_t g_phase_start_ms = 0;
static bool     g_running    = false;  // Chờ lệnh startTraffic từ App trước khi bắt đầu

// Nút bấm
static bool g_btn_red_prev   = true;   // HIGH = không nhấn (pull-up)
static bool g_btn_grn_prev   = true;
static uint32_t g_btn_last_ms = 0;

// WiFi + MQTT
static WiFiClient   g_wifi_client;
static PubSubClient g_mqtt(g_wifi_client);

static char g_topic_pub[80];   // KAI/pcb/{DEVICE_NAME}/telemetry
static char g_topic_sub[80];   // KAI/pcb/{DEVICE_NAME}/cmd

static uint32_t g_last_mqtt_reconnect_ms = 0;
static uint32_t g_last_telemetry_ms      = 0;

// ─── Forward declarations ─────────────────────────────────────────────────────
static void applyState(TlState state);
static void setMode(TlMode mode);
static void displayCountdown(int seconds);
static void publishTelemetry();
static void mqttCallback(char *topic, byte *payload, unsigned int length);
static bool mqttReconnect();
static void connectWifi();
static void checkButtons();
static uint32_t getPhaseDurationMs();
static uint32_t getRemainSec();
static const char *stateStr();
static const char *modeStr();

// ═════════════════════════════════════════════════════════════════════════════
// SETUP
// ═════════════════════════════════════════════════════════════════════════════
void setup()
{
    Serial.begin(115200);
    Serial.println("\n--- ESP32_PCB Traffic Light Controller ---");

    // ── GPIO đèn ──────────────────────────────────────────────────────────────
    pinMode(TL_PIN_RED,    OUTPUT);
    pinMode(TL_PIN_YELLOW, OUTPUT);
    pinMode(TL_PIN_GREEN,  OUTPUT);
    digitalWrite(TL_PIN_RED,    LOW);
    digitalWrite(TL_PIN_YELLOW, LOW);
    digitalWrite(TL_PIN_GREEN,  LOW);

    // ── GPIO Shift Register ───────────────────────────────────────────────────
    pinMode(TL_PIN_SDI,   OUTPUT);
    pinMode(TL_PIN_SCL,   OUTPUT);
    pinMode(TL_PIN_KLOAD, OUTPUT);

    // ── GPIO Nút bấm (pull-up nội bộ) ────────────────────────────────────────
    pinMode(TL_PIN_BTN_RED,   INPUT_PULLUP);
    pinMode(TL_PIN_BTN_GREEN, INPUT_PULLUP);

    // ── MQTT topics ───────────────────────────────────────────────────────────
    snprintf(g_topic_pub, sizeof(g_topic_pub), "KAI/pcb/%s/telemetry", DEVICE_NAME);
    snprintf(g_topic_sub, sizeof(g_topic_sub), "KAI/pcb/%s/cmd",       DEVICE_NAME);

    // ── WiFi ──────────────────────────────────────────────────────────────────
    Serial.println("\n[SETUP] Connecting WiFi first...");
    connectWifi();
    Serial.println("[SETUP] WiFi done.\n");

    // ── MQTT ──────────────────────────────────────────────────────────────────
    Serial.println("[SETUP] Initializing MQTT...");
    g_mqtt.setServer(MQTT_BROKER_IP, MQTT_BROKER_PORT);
    g_mqtt.setCallback(mqttCallback);
    g_mqtt.setBufferSize(512);
    g_mqtt.setKeepAlive(60);  // 60 sec keepalive
    Serial.println("[SETUP] MQTT configured.\n");

    // ── Chờ lệnh startTraffic từ App ────────────────────────────────────
    g_phase_start_ms = millis();
    // Tắt hết đèn khi khởi động — chờ App ra lệnh startTraffic
    digitalWrite(TL_PIN_RED,    LOW);
    digitalWrite(TL_PIN_YELLOW, LOW);
    digitalWrite(TL_PIN_GREEN,  LOW);
    g_running = false;

    Serial.printf("READY | device=%s broker=%s:%d\n",
                  DEVICE_NAME, MQTT_BROKER_IP, MQTT_BROKER_PORT);
    Serial.println("READY | Waiting for startTraffic command from App...");
}

// ═════════════════════════════════════════════════════════════════════════════
// LOOP
// ═════════════════════════════════════════════════════════════════════════════
void loop()
{
    uint32_t now = millis();

    // ── WiFi watchdog ─────────────────────────────────────────────────────────
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi lost — reconnecting...");
        connectWifi();
    }

    // ── MQTT keepalive + reconnect ────────────────────────────────────────────
    if (!g_mqtt.connected()) {
        if ((now - g_last_mqtt_reconnect_ms) >= MQTT_RECONNECT_MS) {
            g_last_mqtt_reconnect_ms = now;
            mqttReconnect();
        }
    } else {
        g_mqtt.loop();
    }

    // ── Nút bấm ───────────────────────────────────────────────────────────────
    checkButtons();

    // ── Chu kỳ đèn (chỉ khi đang chạy và normal mode) ────────────────────────
    if (g_running && g_mode == TL_NORMAL) {
        uint32_t elapsed = now - g_phase_start_ms;
        uint32_t duration = getPhaseDurationMs();
        if (elapsed >= duration) {
            switch (g_state) {
            case TL_RED:    applyState(TL_GREEN);  break;
            case TL_GREEN:  applyState(TL_YELLOW); break;
            case TL_YELLOW: applyState(TL_RED);    break;
            }
        }
    }

    // ── Hiển thị số đếm ngược trên 7-seg ─────────────────────────────────────
    if (g_running) {
        displayCountdown((int)getRemainSec());
    } else {
        displayCountdown(0);  // hiển thị 00 khi dừng
    }

    // ── Publish telemetry định kỳ ────────────────────────────────────────────
    if ((now - g_last_telemetry_ms) >= TELEMETRY_INTERVAL_MS) {
        g_last_telemetry_ms = now;
        publishTelemetry();
    }
}

// ═════════════════════════════════════════════════════════════════════════════
// TRAFFIC LIGHT CONTROL
// ═════════════════════════════════════════════════════════════════════════════

static void applyState(TlState state)
{
    g_state = state;
    g_phase_start_ms = millis();

    digitalWrite(TL_PIN_RED,    state == TL_RED    ? HIGH : LOW);
    digitalWrite(TL_PIN_YELLOW, state == TL_YELLOW ? HIGH : LOW);
    digitalWrite(TL_PIN_GREEN,  state == TL_GREEN  ? HIGH : LOW);

    Serial.printf("LIGHT | %s (mode=%s)\n", stateStr(), modeStr());
    publishTelemetry();  // publish ngay khi đổi trạng thái
}

static void setMode(TlMode mode)
{
    g_mode = mode;
    switch (mode) {
    case TL_NORMAL:
        Serial.println("MODE | normal");
        break;
    case TL_EMERGENCY_RED:
        applyState(TL_RED);
        Serial.println("MODE | emergency_red");
        break;
    case TL_EMERGENCY_GREEN:
        applyState(TL_GREEN);
        Serial.println("MODE | emergency_green");
        break;
    }
    publishTelemetry();
}

static uint32_t getPhaseDurationMs()
{
    switch (g_state) {
    case TL_RED:    return g_red_ms;
    case TL_YELLOW: return g_yellow_ms;
    case TL_GREEN:  return g_green_ms;
    default:        return g_red_ms;
    }
}

static uint32_t getRemainSec()
{
    uint32_t elapsed  = millis() - g_phase_start_ms;
    uint32_t duration = getPhaseDurationMs();
    if (elapsed >= duration) return 0;
    uint32_t remain_ms = duration - elapsed;
    return (remain_ms + 999U) / 1000U;
}

static const char *stateStr()
{
    switch (g_state) {
    case TL_RED:    return "RED";
    case TL_YELLOW: return "YELLOW";
    case TL_GREEN:  return "GREEN";
    default:        return "UNKNOWN";
    }
}

static const char *modeStr()
{
    switch (g_mode) {
    case TL_NORMAL:          return "normal";
    case TL_EMERGENCY_RED:   return "emergency_red";
    case TL_EMERGENCY_GREEN: return "emergency_green";
    default:                 return "unknown";
    }
}

// ─── LED 7 đoạn ──────────────────────────────────────────────────────────────
static void displayCountdown(int seconds)
{
    if (seconds < 0)  seconds = 0;
    if (seconds > 99) seconds = 99;

    int tens  = seconds / 10;
    int units = seconds % 10;

    digitalWrite(TL_PIN_KLOAD, LOW);
    shiftOut(TL_PIN_SDI, TL_PIN_SCL, MSBFIRST, numCode[units]);
    shiftOut(TL_PIN_SDI, TL_PIN_SCL, MSBFIRST, numCode[tens]);
    digitalWrite(TL_PIN_KLOAD, HIGH);
}

// ═════════════════════════════════════════════════════════════════════════════
// NÚT BẤM
// ═════════════════════════════════════════════════════════════════════════════
static void checkButtons()
{
    uint32_t now = millis();
    if ((now - g_btn_last_ms) < BTN_DEBOUNCE_MS) return;

    bool btn_red = (bool)digitalRead(TL_PIN_BTN_RED);    // LOW = nhấn
    bool btn_grn = (bool)digitalRead(TL_PIN_BTN_GREEN);

    // Cạnh xuống nút đỏ → toggle emergency red
    if (g_btn_red_prev && !btn_red) {
        g_btn_last_ms = now;
        TlMode next = (g_mode == TL_EMERGENCY_RED) ? TL_NORMAL : TL_EMERGENCY_RED;
        setMode(next);
        Serial.printf("BTN | red pressed → mode=%s\n", modeStr());
    }

    // Cạnh xuống nút xanh → toggle emergency green
    if (g_btn_grn_prev && !btn_grn) {
        g_btn_last_ms = now;
        TlMode next = (g_mode == TL_EMERGENCY_GREEN) ? TL_NORMAL : TL_EMERGENCY_GREEN;
        setMode(next);
        Serial.printf("BTN | green pressed → mode=%s\n", modeStr());
    }

    g_btn_red_prev = btn_red;
    g_btn_grn_prev = btn_grn;
}

// ═════════════════════════════════════════════════════════════════════════════
// MQTT
// ═════════════════════════════════════════════════════════════════════════════

static void publishTelemetry()
{
    if (!g_mqtt.connected()) return;

    // Build JSON bằng ArduinoJson
    StaticJsonDocument<256> doc;
    doc["light_state"]     = stateStr();
    doc["operation_mode"]  = modeStr();
    doc["remain_sec"]      = (int)getRemainSec();
    doc["tl_red_ms"]       = (int)g_red_ms;
    doc["tl_yellow_ms"]    = (int)g_yellow_ms;
    doc["tl_green_ms"]     = (int)g_green_ms;
    doc["btn_red_pressed"] = !digitalRead(TL_PIN_BTN_RED);   // true khi đang nhấn
    doc["btn_grn_pressed"] = !digitalRead(TL_PIN_BTN_GREEN);
    doc["device"]          = DEVICE_NAME;
    doc["running"]         = g_running;  // trạng thái chạy (do App kiểm soát)

    char buf[256];
    serializeJson(doc, buf, sizeof(buf));
    g_mqtt.publish(g_topic_pub, buf, false);  // retained=false
}

// ─── Nhận lệnh từ App Python ─────────────────────────────────────────────────
static void mqttCallback(char *topic, byte *payload, unsigned int length)
{
    // Null-terminate payload
    char buf[256] = {0};
    if (length >= sizeof(buf)) length = sizeof(buf) - 1;
    memcpy(buf, payload, length);

    Serial.printf("MQTT RX [%s]: %s\n", topic, buf);

    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, buf) != DeserializationError::Ok) {
        Serial.println("MQTT | JSON parse error");
        return;
    }

    const char *method = doc["method"] | "";

    if (strcmp(method, "setNormalMode") == 0) {
        if (g_running) setMode(TL_NORMAL);

    } else if (strcmp(method, "setEmergencyRed") == 0) {
        if (g_running) setMode(TL_EMERGENCY_RED);

    } else if (strcmp(method, "setEmergencyGreen") == 0) {
        if (g_running) setMode(TL_EMERGENCY_GREEN);

    } else if (strcmp(method, "startTraffic") == 0) {
        // App kết nối và ra lệnh bắt đầu
        if (!g_running) {
            g_running = true;
            g_mode = TL_NORMAL;
            g_phase_start_ms = millis();
            applyState(TL_RED);  // bắt đầu từ đờ đỏ
            Serial.println("CMD | startTraffic → đèn bắt đầu chạy");
        }
        publishTelemetry();

    } else if (strcmp(method, "stopTraffic") == 0) {
        // App ngắt kết nối hoặc ra lệnh dừng
        g_running = false;
        g_mode = TL_NORMAL;
        // Tắt hết đèn
        digitalWrite(TL_PIN_RED,    LOW);
        digitalWrite(TL_PIN_YELLOW, LOW);
        digitalWrite(TL_PIN_GREEN,  LOW);
        Serial.println("CMD | stopTraffic → đèn tắt hết");
        publishTelemetry();

    } else if (strcmp(method, "getStatus") == 0) {
        // App ping để kiểm tra kết nối
        publishTelemetry();
        Serial.println("CMD | getStatus → phản hồi telemetry");

    } else if (strcmp(method, "setTimings") == 0) {
        JsonObject params = doc["params"];
        if (!params.isNull()) {
            uint32_t r = params["tl_red_ms"]    | (int)g_red_ms;
            uint32_t y = params["tl_yellow_ms"] | (int)g_yellow_ms;
            uint32_t gn = params["tl_green_ms"] | (int)g_green_ms;
            if (r > 0)  g_red_ms    = r;
            if (y > 0)  g_yellow_ms = y;
            if (gn > 0) g_green_ms  = gn;
            Serial.printf("TIMING | R=%lums Y=%lums G=%lums\n",
                          (unsigned long)g_red_ms,
                          (unsigned long)g_yellow_ms,
                          (unsigned long)g_green_ms);
            publishTelemetry();
        }

    } else {
        Serial.printf("MQTT | unknown method: %s\n", method);
    }
}

// ─── MQTT kết nối / reconnect ─────────────────────────────────────────────────
static bool mqttReconnect()
{
    // BƯỚC 1: Kiểm tra WiFi trước
    if (WiFi.status() != WL_CONNECTED) {
        Serial.printf("MQTT | ✗ WiFi not connected (status=%d), skip MQTT\n", WiFi.status());
        return false;
    }

    // BƯỚC 2: Tạo client ID ổn định (không thay đổi lần lần)
    static char client_id[64] = {0};
    static bool id_init = false;
    if (!id_init) {
        snprintf(client_id, sizeof(client_id), "%s-%X", DEVICE_NAME, esp_random());
        id_init = true;
        Serial.printf("[MQTT] Generated stable client_id: %s\n", client_id);
    }

    // BƯỚC 3: Cố gắng kết nối
    Serial.printf("MQTT | connecting to %s:%d as %s ...\n",
                  MQTT_BROKER_IP, MQTT_BROKER_PORT, client_id);

    if (g_mqtt.connect(client_id)) {
        Serial.printf("MQTT | ✓ CONNECTED! Subscribing to %s\n", g_topic_sub);
        g_mqtt.subscribe(g_topic_sub, 1);
        publishTelemetry();
        return true;
    } else {
        // Kết nối thất bại - in lỗi chi tiết
        int state = g_mqtt.state();
        Serial.printf("MQTT | ✗ FAILED rc=%d, retry in %dms\n", state, MQTT_RECONNECT_MS);
        
        // Giải thích lỗi
        switch (state) {
            case -4:
                Serial.println("  └─ ERR -4: Connection timeout (Broker không phản hồi sau 3s)");
                break;
            case -3:
                Serial.println("  └─ ERR -3: Connection lost (Mất kết nối WiFi hoặc broker restart)");
                break;
            case -2:
                Serial.println("  └─ ERR -2: Connection refused (Port đóng hoặc firewall chặn)");
                break;
            case -1:
                Serial.println("  └─ ERR -1: Disconnected (Normal state trước kết nối)");
                break;
            case 1:
                Serial.println("  └─ ERR 1: Bad protocol (MQTT protocol version không match)");
                break;
            case 2:
                Serial.println("  └─ ERR 2: Bad client ID (Client ID bị reject bởi broker)");
                break;
            case 3:
                Serial.println("  └─ ERR 3: Unavailable (Broker not available)");
                break;
            case 4:
                Serial.println("  └─ ERR 4: Bad credentials (Username/password sai)");
                break;
            case 5:
                Serial.println("  └─ ERR 5: Unauthorized (Client không có quyền)");
                break;
            default:
                Serial.printf("  └─ ERR %d: Unknown error\n", state);
        }
        return false;
    }
}

// ─── WiFi ─────────────────────────────────────────────────────────────────────
static void connectWifi()
{
    Serial.printf("WiFi | connecting to '%s' ...\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    uint32_t start = millis();
    int attempt = 0;
    while (WiFi.status() != WL_CONNECTED) {
        if ((millis() - start) >= WIFI_CONNECT_TIMEOUT_MS) {
            Serial.println("\nWiFi | ✗ timeout! Will retry in main loop...");
            return;
        }
        delay(500);
        Serial.print(".");
        attempt++;
        if (attempt % 4 == 0) {
            int status = WiFi.status();
            Serial.printf(" [status=%d]", status);
        }
    }
    Serial.printf("\nWiFi | ✓ CONNECTED!\n");
    Serial.printf("  ├─ IP: %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("  ├─ Gateway: %s\n", WiFi.gatewayIP().toString().c_str());
    Serial.printf("  └─ RSSI: %d dBm\n", WiFi.RSSI());
    
    // Chờ một chút để network ổn định
    delay(500);
}