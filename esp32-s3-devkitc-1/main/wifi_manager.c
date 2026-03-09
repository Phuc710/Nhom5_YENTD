/*
 * wifi_manager.c - Quan ly WiFi STA + SoftAP config portal cho ESP32-S3.
 *
 * Flow:
 *   1. Thu ket noi bang SSID/password da luu trong NVS
 *   2. Neu chua co hoac ket noi that bai -> bat SoftAP
 *   3. Portal HTTP tai 192.168.4.1 cho phep scan va luu WiFi
 *   4. Luu WiFi vao NVS, thu ket noi lai ngay lap tuc
 */
#include "wifi_manager.h"

#include "led_status.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef WIFI_MANAGER_AP_SSID
#error "WIFI_MANAGER_AP_SSID chua duoc dinh nghia. Dat trong platformio.ini."
#endif

#ifndef WIFI_MANAGER_AP_PASS
#error "WIFI_MANAGER_AP_PASS chua duoc dinh nghia. Dat trong platformio.ini."
#endif

static const char *TAG = "wifi_mgr";

#define WIFI_CONNECTED_BIT     BIT0
#define WIFI_DISCONNECTED_BIT  BIT1
#define WIFI_PORTAL_SUBMIT_BIT BIT2

#define WIFI_STATUS_LEN      160
#define WIFI_PORTAL_BODY_MAX 256
#define WIFI_SCAN_MAX_AP     20

static bool s_netif_ready = false;
static bool s_wifi_ready = false;
static bool s_portal_active = false;
static bool s_sta_connected = false;
static esp_netif_t *s_sta_netif = NULL;
static esp_netif_t *s_ap_netif = NULL;
static EventGroupHandle_t s_evt_group = NULL;
static SemaphoreHandle_t s_state_mutex = NULL;
static httpd_handle_t s_portal_httpd = NULL;
static app_config_t *s_active_cfg = NULL;
static char s_status_message[WIFI_STATUS_LEN] = "Đang khởi tạo WiFi";
static int s_last_disconnect_reason = -1;
static esp_event_handler_instance_t s_wifi_evt_instance = NULL;
static esp_event_handler_instance_t s_ip_evt_instance = NULL;

static void set_status_message(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);

    if (s_state_mutex) {
        xSemaphoreTake(s_state_mutex, portMAX_DELAY);
    }
    vsnprintf(s_status_message, sizeof(s_status_message), fmt, args);
    if (s_state_mutex) {
        xSemaphoreGive(s_state_mutex);
    }

    va_end(args);
}

static void get_status_snapshot(
    char *status,
    size_t status_len,
    char *ssid,
    size_t ssid_len,
    bool *connected,
    bool *portal_active
)
{
    if (s_state_mutex) {
        xSemaphoreTake(s_state_mutex, portMAX_DELAY);
    }

    if (status && status_len > 0) {
        snprintf(status, status_len, "%s", s_status_message);
    }
    if (ssid && ssid_len > 0) {
        snprintf(
            ssid,
            ssid_len,
            "%s",
            (s_active_cfg && s_active_cfg->ssid[0]) ? s_active_cfg->ssid : ""
        );
    }
    if (connected) {
        *connected = s_sta_connected;
    }
    if (portal_active) {
        *portal_active = s_portal_active;
    }

    if (s_state_mutex) {
        xSemaphoreGive(s_state_mutex);
    }
}

static esp_err_t read_http_body(httpd_req_t *req, char *buffer, size_t buffer_len)
{
    if (!req || !buffer || buffer_len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (req->content_len <= 0 || req->content_len >= (int)buffer_len) {
        return ESP_ERR_INVALID_SIZE;
    }

    int total = 0;
    while (total < req->content_len) {
        int ret = httpd_req_recv(req, buffer + total, req->content_len - total);
        if (ret <= 0) {
            return ESP_FAIL;
        }
        total += ret;
    }

    buffer[total] = '\0';
    return ESP_OK;
}

static bool is_hex_char(char c)
{
    return (c >= '0' && c <= '9') ||
           (c >= 'a' && c <= 'f') ||
           (c >= 'A' && c <= 'F');
}

static char hex_to_char(char high, char low)
{
    int hi = (high <= '9') ? (high - '0') : ((high & ~0x20) - 'A' + 10);
    int lo = (low <= '9') ? (low - '0') : ((low & ~0x20) - 'A' + 10);
    return (char)((hi << 4) | lo);
}

static void url_decode_inplace(char *text)
{
    if (!text) {
        return;
    }

    char *src = text;
    char *dst = text;
    while (*src) {
        if (*src == '+') {
            *dst++ = ' ';
            src++;
        } else if (*src == '%' && is_hex_char(src[1]) && is_hex_char(src[2])) {
            *dst++ = hex_to_char(src[1], src[2]);
            src += 3;
        } else {
            *dst++ = *src++;
        }
    }
    *dst = '\0';
}

static bool parse_wifi_form(char *body, char *ssid, size_t ssid_len, char *password, size_t pass_len)
{
    if (!body || !ssid || !password) {
        return false;
    }

    ssid[0] = '\0';
    password[0] = '\0';

    char *saveptr = NULL;
    for (char *pair = strtok_r(body, "&", &saveptr);
         pair;
         pair = strtok_r(NULL, "&", &saveptr)) {
        char *eq = strchr(pair, '=');
        if (!eq) {
            continue;
        }

        *eq = '\0';
        char *key = pair;
        char *value = eq + 1;
        url_decode_inplace(key);
        url_decode_inplace(value);

        if (strcmp(key, "ssid") == 0) {
            snprintf(ssid, ssid_len, "%s", value);
        } else if (strcmp(key, "password") == 0) {
            snprintf(password, pass_len, "%s", value);
        }
    }

    return ssid[0] != '\0';
}

static size_t json_append_escaped(char *buffer, size_t buffer_len, size_t offset, const char *text)
{
    if (!buffer || !text || offset >= buffer_len) {
        return offset;
    }

    for (const char *p = text; *p && offset + 2 < buffer_len; ++p) {
        if (*p == '"' || *p == '\\') {
            buffer[offset++] = '\\';
            buffer[offset++] = *p;
        } else if ((unsigned char)*p < 0x20) {
            buffer[offset++] = ' ';
        } else {
            buffer[offset++] = *p;
        }
    }
    buffer[offset] = '\0';
    return offset;
}

static esp_err_t wifi_start_or_reuse(void)
{
    esp_err_t err = esp_wifi_start();
    if (err == ESP_OK || err == ESP_ERR_WIFI_CONN) {
        return ESP_OK;
    }
    return err;
}

static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *event = (wifi_event_sta_disconnected_t *)data;
        s_last_disconnect_reason = event ? (int)event->reason : -1;
        s_sta_connected = false;
        if (s_evt_group) {
            xEventGroupClearBits(s_evt_group, WIFI_CONNECTED_BIT);
            xEventGroupSetBits(s_evt_group, WIFI_DISCONNECTED_BIT);
        }
        set_status_message("Mất kết nối WiFi, reason=%d", s_last_disconnect_reason);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)data;
        s_sta_connected = true;
        s_last_disconnect_reason = 0;
        if (s_evt_group) {
            xEventGroupClearBits(s_evt_group, WIFI_DISCONNECTED_BIT);
            xEventGroupSetBits(s_evt_group, WIFI_CONNECTED_BIT);
        }
        set_status_message("Đã kết nối và nhận IP " IPSTR, IP2STR(&event->ip_info.ip));
        ESP_LOGI(TAG, "WiFi đã nhận IP: " IPSTR, IP2STR(&event->ip_info.ip));
    }
}

static void ensure_netif(void)
{
    if (s_netif_ready) {
        return;
    }

    esp_err_t err = esp_netif_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(err);
    }

    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(err);
    }

    s_sta_netif = esp_netif_create_default_wifi_sta();
    s_ap_netif = esp_netif_create_default_wifi_ap();
    s_evt_group = xEventGroupCreate();
    s_state_mutex = xSemaphoreCreateMutex();

    if (!s_sta_netif || !s_ap_netif || !s_evt_group || !s_state_mutex) {
        ESP_LOGE(TAG, "Không khởi tạo được tài nguyên WiFi manager");
        abort();
    }

    s_netif_ready = true;
}

static void ensure_wifi_driver(void)
{
    if (s_wifi_ready) {
        return;
    }

    wifi_init_config_t init_cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT,
        ESP_EVENT_ANY_ID,
        &wifi_event_handler,
        NULL,
        &s_wifi_evt_instance
    ));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT,
        IP_EVENT_STA_GOT_IP,
        &wifi_event_handler,
        NULL,
        &s_ip_evt_instance
    ));

    s_wifi_ready = true;
}

static esp_err_t start_config_ap(void)
{
    wifi_config_t ap_cfg = {0};
    snprintf((char *)ap_cfg.ap.ssid, sizeof(ap_cfg.ap.ssid), "%s", WIFI_MANAGER_AP_SSID);
    ap_cfg.ap.ssid_len = strlen((char *)ap_cfg.ap.ssid);
    ap_cfg.ap.max_connection = 4;
    ap_cfg.ap.channel = 1;
    ap_cfg.ap.pmf_cfg.required = false;

    size_t ap_pass_len = strlen(WIFI_MANAGER_AP_PASS);
    if (ap_pass_len >= 8) {
        snprintf((char *)ap_cfg.ap.password, sizeof(ap_cfg.ap.password), "%s", WIFI_MANAGER_AP_PASS);
        ap_cfg.ap.authmode = WIFI_AUTH_WPA2_PSK;
    } else {
        ap_cfg.ap.password[0] = '\0';
        ap_cfg.ap.authmode = WIFI_AUTH_OPEN;
    }

    esp_err_t err = esp_wifi_disconnect();
    if (err != ESP_OK && err != ESP_ERR_WIFI_NOT_CONNECT) {
        ESP_LOGW(TAG, "esp_wifi_disconnect: %s", esp_err_to_name(err));
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_cfg));
    ESP_ERROR_CHECK(wifi_start_or_reuse());

    s_portal_active = true;
    esp_netif_ip_info_t ap_ip = {0};
    const bool has_ap_ip = s_ap_netif && esp_netif_get_ip_info(s_ap_netif, &ap_ip) == ESP_OK;
    char ap_ip_str[16] = "192.168.4.1";
    if (has_ap_ip) {
        snprintf(ap_ip_str, sizeof(ap_ip_str), IPSTR, IP2STR(&ap_ip.ip));
    }
    if (ap_pass_len >= 8) {
        set_status_message("AP %s đã bật. Truy cập %s để cấu hình", WIFI_MANAGER_AP_SSID, ap_ip_str);
        ESP_LOGW(
            TAG,
            "Bật SoftAP cấu hình: SSID=%s, truy cập http://%s/",
            WIFI_MANAGER_AP_SSID,
            ap_ip_str
        );
    } else {
        set_status_message("AP open %s đã bật tại %s", WIFI_MANAGER_AP_SSID, ap_ip_str);
        ESP_LOGW(
            TAG,
            "Bật SoftAP open: SSID=%s, IP=%s (wifi_ap_pass ngắn hơn 8 ký tự nên không bật WPA2)",
            WIFI_MANAGER_AP_SSID,
            ap_ip_str
        );
    }

    return ESP_OK;
}

static void stop_config_ap(void)
{
    if (s_portal_httpd) {
        httpd_stop(s_portal_httpd);
        s_portal_httpd = NULL;
    }

    s_portal_active = false;
    esp_err_t err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Không chuyển được sang STA-only: %s", esp_err_to_name(err));
    }
}

static bool wifi_connect_sta(const char *ssid, const char *password, int max_retry, bool keep_ap_active)
{
    if (!ssid || ssid[0] == '\0') {
        ESP_LOGW(TAG, "Chưa có SSID để kết nối");
        return false;
    }

    wifi_config_t sta_cfg = {0};
    snprintf((char *)sta_cfg.sta.ssid, sizeof(sta_cfg.sta.ssid), "%s", ssid);
    snprintf((char *)sta_cfg.sta.password, sizeof(sta_cfg.sta.password), "%s", password ? password : "");
    sta_cfg.sta.threshold.authmode = WIFI_AUTH_OPEN;
    sta_cfg.sta.pmf_cfg.capable = true;
    sta_cfg.sta.pmf_cfg.required = false;

    xEventGroupClearBits(s_evt_group, WIFI_CONNECTED_BIT | WIFI_DISCONNECTED_BIT);

    ESP_ERROR_CHECK(esp_wifi_set_mode(keep_ap_active ? WIFI_MODE_APSTA : WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta_cfg));
    ESP_ERROR_CHECK(wifi_start_or_reuse());

    led_status_set_rgb(32, 24, 0);
    set_status_message("Đang thử kết nối SSID %s", ssid);
    ESP_LOGI(TAG, "Đang kết nối SSID \"%s\" (%d lần thử)", ssid, max_retry);

    for (int attempt = 1; attempt <= max_retry; ++attempt) {
        xEventGroupClearBits(s_evt_group, WIFI_CONNECTED_BIT | WIFI_DISCONNECTED_BIT);
        esp_err_t err = esp_wifi_connect();
        if (err != ESP_OK && err != ESP_ERR_WIFI_CONN) {
            ESP_LOGW(TAG, "esp_wifi_connect thất bại: %s", esp_err_to_name(err));
        }

        EventBits_t bits = xEventGroupWaitBits(
            s_evt_group,
            WIFI_CONNECTED_BIT | WIFI_DISCONNECTED_BIT,
            pdTRUE,
            pdFALSE,
            pdMS_TO_TICKS(7000)
        );

        if (bits & WIFI_CONNECTED_BIT) {
            led_status_set_rgb(0, 48, 0);
            set_status_message("Kết nối WiFi thành công: %s", ssid);
            ESP_LOGI(TAG, "WiFi kết nối thành công");
            return true;
        }

        ESP_LOGW(
            TAG,
            "Lần thử %d/%d thất bại (reason=%d)",
            attempt,
            max_retry,
            s_last_disconnect_reason
        );
        set_status_message(
            "Kết nối thất bại lần %d/%d, reason=%d",
            attempt,
            max_retry,
            s_last_disconnect_reason
        );
        vTaskDelay(pdMS_TO_TICKS(500));
    }

    led_status_set_rgb(48, 0, 0);
    set_status_message("Không thể kết nối SSID %s", ssid);
    ESP_LOGE(TAG, "Không thể kết nối SSID \"%s\"", ssid);
    return false;
}

static esp_err_t portal_root_handler(httpd_req_t *req)
{
    char saved_ssid[33];
    get_status_snapshot(NULL, 0, saved_ssid, sizeof(saved_ssid), NULL, NULL);

    char html[4096];
    const bool ap_open = strlen(WIFI_MANAGER_AP_PASS) < 8;
    int len = snprintf(
        html,
        sizeof(html),
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>ESP32 WiFi Manager</title>"
        "<style>"
        "body{font-family:system-ui,-apple-system,sans-serif;background:#0b1220;color:#e5edf7;margin:0;padding:24px}"
        ".card{max-width:640px;margin:0 auto;background:#14213d;border:1px solid #243b68;border-radius:18px;padding:24px}"
        "h1{margin:0 0 8px;font-size:28px}p{line-height:1.5;color:#b8c5db}"
        "label{display:block;margin:14px 0 6px;font-weight:700}"
        "input,select,button{width:100%%;padding:12px 14px;border-radius:12px;border:1px solid #33538b;font-size:16px}"
        "input,select{background:#0e1a30;color:#fff}button{background:#f6c445;color:#171717;font-weight:700;cursor:pointer}"
        ".row{display:grid;grid-template-columns:1fr auto;gap:12px}.hint{font-size:14px;color:#9fb0cf}"
        "#status{padding:12px 14px;border-radius:12px;background:#0e1a30;border:1px solid #233659;margin:16px 0}"
        "</style></head><body><div class='card'>"
        "<h1>ESP32 WiFi Manager</h1>"
        "<p>SoftAP đang phát với SSID <b>%s</b>. Truy cập <b>http://192.168.4.1/</b> để cấu hình WiFi.</p>"
        "<p class='hint'>%s</p>"
        "<div id='status'>Đang tải trạng thái...</div>"
        "<div class='row'><select id='scanList'><option value=''>Chọn WiFi từ danh sách</option></select>"
        "<button type='button' id='scanBtn'>Quét WiFi</button></div>"
        "<form id='wifiForm'>"
        "<label for='ssid'>SSID</label>"
        "<input id='ssid' name='ssid' maxlength='32' value='%s' placeholder='Nhập tên WiFi' required>"
        "<label for='password'>Mật khẩu</label>"
        "<input id='password' name='password' maxlength='64' type='password' placeholder='Bỏ trống nếu WiFi open'>"
        "<p class='hint'>Sau khi lưu, ESP32 sẽ tự thử kết nối và tắt AP cấu hình nếu thành công.</p>"
        "<button type='submit'>Lưu và kết nối</button></form></div>"
        "<script>"
        "const statusEl=document.getElementById('status');"
        "const scanList=document.getElementById('scanList');"
        "document.getElementById('scanBtn').onclick=async()=>{"
        "statusEl.textContent='Đang quét WiFi...';"
        "try{const r=await fetch('/api/wifi/scan');const d=await r.json();"
        "scanList.innerHTML=\"<option value=''>Chọn WiFi từ danh sách</option>\";"
        "for(const ssid of d.ssids||[]){const o=document.createElement('option');o.value=ssid;o.textContent=ssid;scanList.appendChild(o);}statusEl.textContent='Quét xong';}"
        "catch(e){statusEl.textContent='Không quét được WiFi';}};"
        "scanList.onchange=()=>{if(scanList.value){document.getElementById('ssid').value=scanList.value;}};"
        "async function refreshStatus(){try{const r=await fetch('/api/wifi/status');const d=await r.json();"
        "statusEl.textContent=d.status + (d.ip ? ' | IP: ' + d.ip : '');}catch(e){statusEl.textContent='Đang chờ ESP32 phản hồi...';}}"
        "setInterval(refreshStatus,2000);refreshStatus();"
        "document.getElementById('wifiForm').onsubmit=async(e)=>{e.preventDefault();"
        "statusEl.textContent='Đang lưu và thử kết nối...';"
        "const form=new URLSearchParams(new FormData(e.target));"
        "try{const r=await fetch('/api/wifi/save',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:form});"
        "const d=await r.json();statusEl.textContent=d.message||d.detail||'Đã gửi cấu hình';}"
        "catch(err){statusEl.textContent='Không gửi được cấu hình';}};"
        "</script></body></html>",
        WIFI_MANAGER_AP_SSID,
        ap_open
            ? "wifi_ap_pass đang ngắn hơn 8 ký tự nên ESP32 sẽ phát open AP theo giới hạn SoftAP của ESP-IDF."
            : "Kết nối vào AP bằng mật khẩu đã đặt trong platformio.ini.",
        saved_ssid
    );

    if (len < 0 || len >= (int)sizeof(html)) {
        return ESP_FAIL;
    }

    httpd_resp_set_type(req, "text/html");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_send(req, html, len);
}

static esp_err_t portal_status_handler(httpd_req_t *req)
{
    char status[WIFI_STATUS_LEN];
    char ssid[33];
    char ip[16] = "";
    bool connected = false;
    bool portal_active = false;

    get_status_snapshot(
        status,
        sizeof(status),
        ssid,
        sizeof(ssid),
        &connected,
        &portal_active
    );
    wifi_get_ip_string(ip, sizeof(ip));

    char response[512];
    size_t offset = 0;
    offset += snprintf(
        response + offset,
        sizeof(response) - offset,
        "{\"connected\":%s,\"portal_active\":%s,\"ap_ssid\":\"",
        connected ? "true" : "false",
        portal_active ? "true" : "false"
    );
    offset = json_append_escaped(response, sizeof(response), offset, WIFI_MANAGER_AP_SSID);
    offset += snprintf(response + offset, sizeof(response) - offset, "\",\"ssid\":\"");
    offset = json_append_escaped(response, sizeof(response), offset, ssid);
    offset += snprintf(response + offset, sizeof(response) - offset, "\",\"ip\":\"");
    offset = json_append_escaped(response, sizeof(response), offset, ip);
    offset += snprintf(response + offset, sizeof(response) - offset, "\",\"status\":\"");
    offset = json_append_escaped(response, sizeof(response), offset, status);
    offset += snprintf(response + offset, sizeof(response) - offset, "\"}");

    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(req, response);
}

static esp_err_t portal_scan_handler(httpd_req_t *req)
{
    wifi_scan_config_t scan_cfg = {0};
    esp_err_t err = esp_wifi_scan_start(&scan_cfg, true);
    if (err != ESP_OK) {
        httpd_resp_set_status(req, "503 Service Unavailable");
        httpd_resp_set_type(req, "application/json");
        return httpd_resp_sendstr(req, "{\"detail\":\"Không quét được WiFi lúc này\"}");
    }

    uint16_t ap_count = 0;
    ESP_ERROR_CHECK(esp_wifi_scan_get_ap_num(&ap_count));
    if (ap_count > WIFI_SCAN_MAX_AP) {
        ap_count = WIFI_SCAN_MAX_AP;
    }

    wifi_ap_record_t records[WIFI_SCAN_MAX_AP] = {0};
    ESP_ERROR_CHECK(esp_wifi_scan_get_ap_records(&ap_count, records));

    char response[2048];
    size_t offset = snprintf(response, sizeof(response), "{\"ssids\":[");
    bool first = true;

    for (uint16_t i = 0; i < ap_count; ++i) {
        const char *ssid = (const char *)records[i].ssid;
        if (!ssid[0]) {
            continue;
        }

        bool duplicate = false;
        for (uint16_t j = 0; j < i; ++j) {
            if (strcmp(ssid, (const char *)records[j].ssid) == 0) {
                duplicate = true;
                break;
            }
        }
        if (duplicate) {
            continue;
        }

        offset += snprintf(response + offset, sizeof(response) - offset, "%s\"", first ? "" : ",");
        offset = json_append_escaped(response, sizeof(response), offset, ssid);
        offset += snprintf(response + offset, sizeof(response) - offset, "\"");
        first = false;
    }

    snprintf(response + offset, sizeof(response) - offset, "]}");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(req, response);
}

static esp_err_t portal_save_handler(httpd_req_t *req)
{
    if (!s_active_cfg) {
        httpd_resp_set_status(req, "503 Service Unavailable");
        httpd_resp_set_type(req, "application/json");
        return httpd_resp_sendstr(req, "{\"detail\":\"Chưa sẵn sàng lưu cấu hình\"}");
    }

    char body[WIFI_PORTAL_BODY_MAX];
    if (read_http_body(req, body, sizeof(body)) != ESP_OK) {
        httpd_resp_set_status(req, "400 Bad Request");
        httpd_resp_set_type(req, "application/json");
        return httpd_resp_sendstr(req, "{\"detail\":\"Nội dung request không hợp lệ\"}");
    }

    char ssid[33];
    char password[65];
    if (!parse_wifi_form(body, ssid, sizeof(ssid), password, sizeof(password))) {
        httpd_resp_set_status(req, "400 Bad Request");
        httpd_resp_set_type(req, "application/json");
        return httpd_resp_sendstr(req, "{\"detail\":\"SSID không được để trống\"}");
    }

    snprintf(s_active_cfg->ssid, sizeof(s_active_cfg->ssid), "%s", ssid);
    snprintf(s_active_cfg->password, sizeof(s_active_cfg->password), "%s", password);

    if (app_config_save(s_active_cfg) != ESP_OK) {
        httpd_resp_set_status(req, "500 Internal Server Error");
        httpd_resp_set_type(req, "application/json");
        return httpd_resp_sendstr(req, "{\"detail\":\"Không lưu được WiFi vào NVS\"}");
    }

    set_status_message("Đã lưu SSID %s, đang thử kết nối", ssid);
    xEventGroupSetBits(s_evt_group, WIFI_PORTAL_SUBMIT_BIT);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(
        req,
        "{\"success\":true,\"message\":\"Đã lưu WiFi. ESP32 đang thử kết nối...\"}"
    );
}

static esp_err_t portal_redirect_handler(httpd_req_t *req)
{
    httpd_resp_set_status(req, "302 Found");
    httpd_resp_set_hdr(req, "Location", "/");
    return httpd_resp_send(req, NULL, 0);
}

static esp_err_t start_portal_server(void)
{
    if (s_portal_httpd) {
        return ESP_OK;
    }

    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.max_uri_handlers = 10;
    config.stack_size = 8192;

    esp_err_t err = httpd_start(&s_portal_httpd, &config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Không khởi động được WiFi portal: %s", esp_err_to_name(err));
        return err;
    }

    httpd_uri_t root_uri = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = portal_root_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t status_uri = {
        .uri = "/api/wifi/status",
        .method = HTTP_GET,
        .handler = portal_status_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t scan_uri = {
        .uri = "/api/wifi/scan",
        .method = HTTP_GET,
        .handler = portal_scan_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t save_uri = {
        .uri = "/api/wifi/save",
        .method = HTTP_POST,
        .handler = portal_save_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t android_uri = {
        .uri = "/generate_204",
        .method = HTTP_GET,
        .handler = portal_redirect_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t apple_uri = {
        .uri = "/hotspot-detect.html",
        .method = HTTP_GET,
        .handler = portal_redirect_handler,
        .user_ctx = NULL,
    };

    httpd_register_uri_handler(s_portal_httpd, &root_uri);
    httpd_register_uri_handler(s_portal_httpd, &status_uri);
    httpd_register_uri_handler(s_portal_httpd, &scan_uri);
    httpd_register_uri_handler(s_portal_httpd, &save_uri);
    httpd_register_uri_handler(s_portal_httpd, &android_uri);
    httpd_register_uri_handler(s_portal_httpd, &apple_uri);

    ESP_LOGI(TAG, "WiFi portal đã sẵn sàng tại http://192.168.4.1/");
    return ESP_OK;
}

void wifi_manager_init(void)
{
    ensure_netif();
    ensure_wifi_driver();
}

bool wifi_manager_ensure_connected(app_config_t *cfg, int max_retry)
{
    if (!cfg) {
        return false;
    }

    wifi_manager_init();
    s_active_cfg = cfg;

    if (cfg->ssid[0] && wifi_connect_sta(cfg->ssid, cfg->password, max_retry, false)) {
        return true;
    }

    if (start_config_ap() != ESP_OK || start_portal_server() != ESP_OK) {
        return false;
    }

    led_status_set_rgb(32, 0, 32);
    set_status_message("Đang chờ cấu hình WiFi qua AP %s", WIFI_MANAGER_AP_SSID);

    while (true) {
        xEventGroupWaitBits(
            s_evt_group,
            WIFI_PORTAL_SUBMIT_BIT,
            pdTRUE,
            pdFALSE,
            portMAX_DELAY
        );

        if (!cfg->ssid[0]) {
            continue;
        }

        led_status_set_rgb(32, 24, 0);
        if (wifi_connect_sta(cfg->ssid, cfg->password, max_retry, true)) {
            stop_config_ap();
            return true;
        }

        led_status_set_rgb(48, 0, 0);
        set_status_message("Kết nối thất bại. Mở lại 192.168.4.1 để nhập WiFi khác");
    }
}

bool wifi_get_ip_string(char *buffer, size_t buffer_len)
{
    if (!buffer || buffer_len < 16) {
        return false;
    }

    if (!s_sta_netif) {
        return false;
    }

    esp_netif_ip_info_t ip_info = {0};
    if (esp_netif_get_ip_info(s_sta_netif, &ip_info) != ESP_OK || ip_info.ip.addr == 0) {
        return false;
    }

    snprintf(buffer, buffer_len, IPSTR, IP2STR(&ip_info.ip));
    return true;
}
