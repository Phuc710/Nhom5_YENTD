#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFiManager.h>   // tzapu/WiFiManager

// ======================== CONFIG =========================
static const char* HTTP_PROVISION_URL = "https://tcm-iot.imespro.ai/api/v1/provision";
static const char* MQTT_HOST          = "103.249.117.212";
static const int   MQTT_PORT          = 1883;

// Provision key/secret của Device Profile (bạn đang có trên màn hình)
static const char* PROVISION_DEVICE_KEY    = "3scp0hz740plm9k15vfj";
static const char* PROVISION_DEVICE_SECRET = "u7qws1jjqkecseragn3o";

// Nếu bạn muốn prefix theo lô (camera, sensor...)
static const char* DEVICE_PREFIX = "IMES_Cam_";

// ======================== GLOBALS =========================
Preferences prefs;

WiFiClient espClient;
PubSubClient mqtt(espClient);

WiFiClientSecure secureClient; // dùng cho HTTPS provisioning

String deviceName;
String accessToken;

unsigned long lastSend = 0;
int mqttFailCount = 0;

static String macSuffix() {
  uint8_t mac[6];
  WiFi.macAddress(mac);
  char buf[13];
  snprintf(buf, sizeof(buf), "%02X%02X%02X%02X%02X%02X",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  return String(buf);
}

static void loadFromFlash() {
  prefs.begin("imes", false);
  accessToken = prefs.getString("token", "");
  prefs.end();
}

static void saveTokenToFlash(const String& token) {
  prefs.begin("imes", false);
  prefs.putString("token", token);
  prefs.end();
}

static void clearTokenInFlash() {
  prefs.begin("imes", false);
  prefs.remove("token");
  prefs.end();
  accessToken = "";
}

static void ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  WiFiManager wm;
  wm.setConfigPortalTimeout(180);           // 3 phút
  wm.setConnectTimeout(20);
  wm.setCaptivePortalEnable(true);

  String apName = String("ESP32_SETUP_") + macSuffix().substring(6); // gọn
  bool ok = wm.autoConnect(apName.c_str()); // nếu chưa có WiFi -> tự bật portal
  if (!ok) {
    ESP.restart();
  }
}

static bool doProvision() {
  // HTTPS: setInsecure() để demo (production thì nên pin CA/cert)
  secureClient.setInsecure();

  HTTPClient http;
  http.begin(secureClient, HTTP_PROVISION_URL);
  http.addHeader("Content-Type", "application/json");

  // Body provisioning chuẩn ThingsBoard:
  // {"deviceName":"...","provisionDeviceKey":"...","provisionDeviceSecret":"..."}
  StaticJsonDocument<256> doc;
  doc["deviceName"] = deviceName;
  doc["provisionDeviceKey"] = PROVISION_DEVICE_KEY;
  doc["provisionDeviceSecret"] = PROVISION_DEVICE_SECRET;

  String body;
  serializeJson(doc, body);

  int code = http.POST(body);
  String resp = http.getString();
  http.end();

  if (code < 200 || code >= 300) {
    Serial.printf("[TB] Provision HTTP %d\n", code);
    return false;
  }

  StaticJsonDocument<512> out;
  DeserializationError err = deserializeJson(out, resp);
  if (err) {
    Serial.println("[TB] Provision JSON parse fail");
    return false;
  }

  // Thường trả về "credentialsValue" hoặc "token" hoặc "ACCESS_TOKEN" tuỳ bản
  String token = "";
  if (out.containsKey("credentialsValue")) token = (const char*)out["credentialsValue"];
  else if (out.containsKey("token"))       token = (const char*)out["token"];
  else if (out.containsKey("ACCESS_TOKEN"))token = (const char*)out["ACCESS_TOKEN"];

  if (token.length() == 0) {
    Serial.println("[TB] Provision ok but NO token field!");
    return false;
  }

  accessToken = token;
  saveTokenToFlash(accessToken);
  Serial.println("[TB] Provision OK -> token saved");
  return true;
}

static bool mqttConnectWithToken() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);

  // ThingsBoard MQTT: clientId bất kỳ, username = ACCESS_TOKEN, password bỏ trống
  String clientId = "esp32-" + macSuffix();

  bool ok = mqtt.connect(clientId.c_str(), accessToken.c_str(), "");
  if (!ok) {
    int st = mqtt.state();
    Serial.printf("[MQTT] connect fail, state=%d\n", st);

    // 5 = not authorized (token sai / device bị xóa / token bị rotate)
    if (st == 5) {
      Serial.println("[AUTO] Token invalid -> clear token & reprovision");
      clearTokenInFlash();
    }
    return false;
  }

  Serial.println("[MQTT] connected!");
  mqttFailCount = 0;
  return true;
}

static void ensureTBOnline() {
  if (accessToken.length() == 0) {
    // chưa có token -> provision (sẽ tự tạo device nếu profile cho phép)
    Serial.println("[AUTO] No token -> provisioning...");
    if (!doProvision()) return;
  }

  if (!mqtt.connected()) {
    if (!mqttConnectWithToken()) {
      mqttFailCount++;

      // Nếu fail nhiều lần (router chập chờn), vẫn thử provision lại khi token bị clear
      if (accessToken.length() == 0) {
        delay(1000);
        doProvision();
      }
      delay(1000);
      return;
    }
  }

  mqtt.loop();
}

static void sendTelemetryEvery500ms() {
  if (!mqtt.connected()) return;

  unsigned long now = millis();
  if (now - lastSend < 500) return;
  lastSend = now;

  // demo data
  float temp = 25.0 + (float)(esp_random() % 1000) / 100.0; // 25..35
  float hum  = 40.0 + (float)(esp_random() % 2000) / 100.0; // 40..60

  StaticJsonDocument<256> doc;
  doc["temp"] = temp;
  doc["humidity"] = hum;

  String payload;
  serializeJson(doc, payload);

  bool ok = mqtt.publish("v1/devices/me/telemetry", payload.c_str());
  if (!ok) {
    Serial.println("[MQTT] publish fail");
  } else {
    Serial.printf("[MQTT] telemetry: %s\n", payload.c_str());
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);

  deviceName = String(DEVICE_PREFIX) + macSuffix();
  Serial.println("===== ESP32 IMES PRO AUTO =====");
  Serial.println("DeviceName: " + deviceName);

  loadFromFlash();

  ensureWiFi();       // có WiFi thì vào STA, chưa có thì bật captive portal
  ensureTBOnline();   // có token thì MQTT, không có thì provision
}

void loop() {
  ensureWiFi();
  ensureTBOnline();

  // gửi mỗi 500ms (đúng yêu cầu)
  sendTelemetryEvery500ms();
}
