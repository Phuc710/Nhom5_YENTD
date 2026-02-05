#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// =========================
// WIFI
// =========================
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

// =========================
// MQTT (PHẢI TRÙNG server/config.env)
// =========================
const char* MQTT_HOST = "broker.hivemq.com";
const int   MQTT_PORT = 1883;

const char* TOPIC_CONTROL   = "traffic/iot/control";
const char* TOPIC_VIOLATION = "traffic/iot/violation";
const char* TOPIC_DEVICE    = "traffic/iot/device";
const char* TOPIC_ALERT     = "traffic/iot/alert";
const char* TOPIC_COMMAND   = "traffic/iot/command";

// =========================
// DEVICE INFO
// =========================
String DEVICE_ID = "ESP32-CAM-01";   // đổi theo node
String DEVICE_NAME = "ESP32-CAM-01";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

// =========================
// TRAFFIC STATE (DEMO LOGIC)
// =========================
String lightStatus = "RED"; // RED/YELLOW/GREEN
int countdown = 30;
bool overrideMode = false;
unsigned long lastTickMs = 0;
unsigned long lastDevicePubMs = 0;

static String ipToString(IPAddress ip){
  return String(ip[0]) + "." + String(ip[1]) + "." + String(ip[2]) + "." + String(ip[3]);
}

void publishJson(const char* topic, JsonDocument& doc) {
  char out[512];
  size_t n = serializeJson(doc, out, sizeof(out));
  mqtt.publish(topic, out, n);
}

void publishDeviceTelemetry() {
  StaticJsonDocument<256> doc;
  doc["id"] = DEVICE_ID;
  doc["name"] = DEVICE_NAME;
  doc["online"] = true;
  doc["rssi"] = WiFi.RSSI();
  doc["battery"] = 85; // nếu có pin thật thì thay bằng ADC
  doc["ip"] = ipToString(WiFi.localIP());
  doc["lastSeen"] = (uint64_t)millis(); // hoặc epoch ms nếu bạn có NTP

  publishJson(TOPIC_DEVICE, doc);
}

void publishControl() {
  StaticJsonDocument<256> doc;
  doc["status"] = lightStatus;     // "RED"|"YELLOW"|"GREEN"
  doc["time"] = countdown;         // number
  doc["override"] = overrideMode;  // boolean
  publishJson(TOPIC_CONTROL, doc);
}

// Vi phạm thật: bạn sẽ thay logic trigger theo AI/ROI/camera
void publishViolationSample() {
  StaticJsonDocument<384> doc;
  doc["plate"] = "59A-123.45";
  doc["type"] = "Xe máy";
  doc["speed"] = "18 km/h";
  doc["image"] = "http://your-esp32-or-server/image.jpg"; // nếu có ảnh thật -> URL thật
  doc["light"] = lightStatus; // thường gửi "RED"
  doc["timestamp"] = (uint32_t)(time(nullptr)); // nếu chưa có NTP thì sẽ là 0
  doc["roi"] = "Vạch dừng (ROI)";

  publishJson(TOPIC_VIOLATION, doc);
}

void publishAlert(const char* level, const char* title, const char* message) {
  StaticJsonDocument<256> doc;
  doc["level"] = level;     // info|warn|err
  doc["title"] = title;
  doc["message"] = message;
  doc["timestamp"] = (uint32_t)(time(nullptr));
  publishJson(TOPIC_ALERT, doc);
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  // TOPIC_COMMAND nhận lệnh từ Web -> Python -> MQTT
  if (String(topic) != TOPIC_COMMAND) return;

  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) {
    publishAlert("err", "CMD JSON ERROR", "Không parse được JSON command");
    return;
  }

  const char* type = doc["type"] | "PING";
  // value có thể là string/bool/number -> đọc mềm
  // Ở web hiện gửi:
  // {type:"EMERGENCY", value:"RED"} hoặc {type:"AUTO", value:true}
  if (String(type) == "EMERGENCY") {
    const char* v = doc["value"] | "RED";
    overrideMode = true;
    lightStatus = String(v);
    countdown = 15; // tuỳ bạn
    publishControl();
    publishAlert("warn", "EMERGENCY", (String("Override -> ") + v).c_str());
    return;
  }

  if (String(type) == "AUTO") {
    bool v = doc["value"] | true;
    if (v) {
      overrideMode = false;
      publishAlert("info", "AUTO MODE", "Resume Auto = true");
    } else {
      publishAlert("warn", "AUTO MODE", "Auto set false");
    }
    publishControl();
    return;
  }

  if (String(type) == "PING") {
    publishAlert("info", "PING", "ESP32 received ping");
    return;
  }
}

void mqttReconnect() {
  while (!mqtt.connected()) {
    String cid = DEVICE_ID + String("_") + String((uint32_t)ESP.getEfuseMac(), HEX);
    if (mqtt.connect(cid.c_str())) {
      mqtt.subscribe(TOPIC_COMMAND);
      publishAlert("info", "MQTT", "ESP32 connected + subscribed command");
      publishDeviceTelemetry();
      publishControl();
    } else {
      delay(1500);
    }
  }
}

void wifiConnect() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(400);
}

void setup() {
  Serial.begin(115200);
  delay(200);

  wifiConnect();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);

  publishAlert("info", "BOOT", "ESP32 started");
}

void loop() {
  if (!mqtt.connected()) mqttReconnect();
  mqtt.loop();

  unsigned long now = millis();

  // publish device telemetry mỗi 3s
  if (now - lastDevicePubMs >= 3000) {
    lastDevicePubMs = now;
    publishDeviceTelemetry();
  }

  // Traffic cycle đơn giản mỗi 1s (khi không override)
  if (now - lastTickMs >= 1000) {
    lastTickMs = now;

    if (!overrideMode) {
      countdown--;
      if (countdown <= 0) {
        if (lightStatus == "GREEN") { lightStatus = "YELLOW"; countdown = 5; }
        else if (lightStatus == "YELLOW") { lightStatus = "RED"; countdown = 15; }
        else { lightStatus = "GREEN"; countdown = 20; }
      }
      publishControl();
    } else {
      // override vẫn publish để UI bám realtime
      publishControl();
    }

    // Nếu muốn test “vi phạm thật” khi đèn đỏ: bật dòng dưới
    // if (lightStatus == "RED" && !overrideMode) publishViolationSample();
  }
}