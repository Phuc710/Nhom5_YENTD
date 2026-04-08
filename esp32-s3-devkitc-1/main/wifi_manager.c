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
#include "mqtt_app.h"
#include "task_manager.h"

#include "dns_server.h"
#include "esp_check.h"
#include "esp_crt_bundle.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_ip_addr.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "lwip/inet.h"
#include "lwip/netdb.h"
#include "lwip/sockets.h"
#include <fcntl.h>
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

#define WIFI_STATUS_LEN         160
#define WIFI_PORTAL_BODY_MAX    256
#define WIFI_SCAN_MAX_AP        20
#define DHCPS_OFFER_DNS         0x02
#define WIFI_PORTAL_CONNECT_RETRY 3
#define WIFI_PORTAL_RESTART_DELAY_MS 1500

#ifndef WIFI_FORCE_PORTAL_ON_BOOT
#error "WIFI_FORCE_PORTAL_ON_BOOT chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef WIFI_CONNECT_TIMEOUT_MS
#error "WIFI_CONNECT_TIMEOUT_MS chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef WIFI_STA_VERIFY_STABLE_MS
#error "WIFI_STA_VERIFY_STABLE_MS chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef WIFI_VERIFY_TIMEOUT_MS
#error "WIFI_VERIFY_TIMEOUT_MS chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef WIFI_VERIFY_URL
#error "WIFI_VERIFY_URL chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef WIFI_VERIFY_LABEL
#error "WIFI_VERIFY_LABEL chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef WIFI_STA_STATIC_IP_ADDR
#error "WIFI_STA_STATIC_IP_ADDR chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef WIFI_STA_STATIC_NETMASK_ADDR
#error "WIFI_STA_STATIC_NETMASK_ADDR chua duoc dinh nghia. Dat trong platformio.ini."
#endif
#ifndef WIFI_STA_STATIC_GW_ADDR
#error "WIFI_STA_STATIC_GW_ADDR chua duoc dinh nghia. Dat trong platformio.ini."
#endif
static bool s_netif_ready = false;
static bool s_wifi_ready = false;
static bool s_portal_active = false;
static bool s_sta_connected = false;
static esp_netif_t *s_sta_netif = NULL;
static esp_netif_t *s_ap_netif = NULL;
static EventGroupHandle_t s_evt_group = NULL;
static SemaphoreHandle_t s_state_mutex = NULL;
static httpd_handle_t s_portal_httpd = NULL;
static dns_server_handle_t s_dns_server = NULL;
static app_config_t *s_active_cfg = NULL;
static char s_captive_portal_uri[64] = {0};
static char s_status_message[WIFI_STATUS_LEN] = "Đang khởi tạo WiFi";
static int s_last_disconnect_reason = -1;
static bool s_portal_restart_pending = false;
static esp_event_handler_instance_t s_wifi_evt_instance = NULL;
static esp_event_handler_instance_t s_ip_evt_instance = NULL;

static void stop_config_ap(void);

static esp_err_t configure_sta_static_ip(void)
{
    if (!s_sta_netif) {
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t err = esp_netif_dhcpc_stop(s_sta_netif);
    if (err != ESP_OK && err != ESP_ERR_ESP_NETIF_DHCP_ALREADY_STOPPED) {
        return err;
    }

    esp_netif_ip_info_t ip_info = {
        .ip.addr = WIFI_STA_STATIC_IP_ADDR,
        .netmask.addr = WIFI_STA_STATIC_NETMASK_ADDR,
        .gw.addr = WIFI_STA_STATIC_GW_ADDR,
    };

    ESP_RETURN_ON_ERROR(
        esp_netif_set_ip_info(s_sta_netif, &ip_info),
        TAG,
        "Khong set duoc IP tinh cho STA"
    );

    esp_netif_dns_info_t dns = {
        .ip.type = ESP_IPADDR_TYPE_V4,
        .ip.u_addr.ip4.addr = WIFI_STA_STATIC_GW_ADDR,
    };

    ESP_RETURN_ON_ERROR(
        esp_netif_set_dns_info(s_sta_netif, ESP_NETIF_DNS_MAIN, &dns),
        TAG,
        "Khong set duoc DNS cho STA"
    );

    ESP_LOGI(
        TAG,
        "STA static IP configured: ip=" IPSTR " mask=" IPSTR " gw=" IPSTR,
        IP2STR(&ip_info.ip),
        IP2STR(&ip_info.netmask),
        IP2STR(&ip_info.gw)
    );

    return ESP_OK;
}

static bool parse_tcp_uri(
    const char *uri,
    char *host,
    size_t host_len,
    uint16_t *port
)
{
    if (!uri || !host || host_len == 0 || !port) {
        return false;
    }

    const char *start = uri;
    uint16_t default_port = 80;
    if (strncmp(uri, "mqtt://", 7) == 0) {
        start = uri + 7;
        default_port = 1883;
    } else if (strncmp(uri, "mqtts://", 8) == 0) {
        start = uri + 8;
        default_port = 8883;
    } else if (strncmp(uri, "http://", 7) == 0) {
        start = uri + 7;
        default_port = 80;
    } else if (strncmp(uri, "https://", 8) == 0) {
        start = uri + 8;
        default_port = 443;
    }

    const char *host_end = start;
    while (*host_end && *host_end != ':' && *host_end != '/') {
        host_end++;
    }

    size_t copy_len = (size_t)(host_end - start);
    if (copy_len == 0 || copy_len >= host_len) {
        return false;
    }

    memcpy(host, start, copy_len);
    host[copy_len] = '\0';
    *port = default_port;

    if (*host_end == ':') {
        long parsed_port = strtol(host_end + 1, NULL, 10);
        if (parsed_port <= 0 || parsed_port > 65535) {
            return false;
        }
        *port = (uint16_t)parsed_port;
    }

    return true;
}

static bool tcp_probe_uri(const char *uri, int timeout_ms, const char *label)
{
    char host[64] = {0};
    uint16_t port = 0;
    if (!parse_tcp_uri(uri, host, sizeof(host), &port)) {
        ESP_LOGW(TAG, "%s probe: invalid uri %s", label ? label : "tcp", uri ? uri : "-");
        return false;
    }

    char port_str[8] = {0};
    snprintf(port_str, sizeof(port_str), "%u", (unsigned)port);

    struct addrinfo hints = {0};
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_family = AF_UNSPEC;

    struct addrinfo *res = NULL;
    int gai_err = getaddrinfo(host, port_str, &hints, &res);
    if (gai_err != 0 || !res) {
        ESP_LOGW(
            TAG,
            "%s probe: DNS failed host=%s port=%s err=%d",
            label ? label : "tcp",
            host,
            port_str,
            gai_err
        );
        return false;
    }

    bool ok = false;
    for (struct addrinfo *it = res; it && !ok; it = it->ai_next) {
        int sock = socket(it->ai_family, it->ai_socktype, it->ai_protocol);
        if (sock < 0) {
            continue;
        }

        int flags = fcntl(sock, F_GETFL, 0);
        if (flags >= 0) {
            fcntl(sock, F_SETFL, flags | O_NONBLOCK);
        }

        int ret = connect(sock, it->ai_addr, it->ai_addrlen);
        if (ret == 0) {
            ok = true;
        } else {
            fd_set write_set;
            FD_ZERO(&write_set);
            FD_SET(sock, &write_set);

            struct timeval tv = {
                .tv_sec = timeout_ms / 1000,
                .tv_usec = (timeout_ms % 1000) * 1000,
            };

            ret = select(sock + 1, NULL, &write_set, NULL, &tv);
            if (ret > 0 && FD_ISSET(sock, &write_set)) {
                int so_error = 0;
                socklen_t so_error_len = sizeof(so_error);
                if (getsockopt(sock, SOL_SOCKET, SO_ERROR, &so_error, &so_error_len) == 0 &&
                    so_error == 0) {
                    ok = true;
                }
            }
        }

        close(sock);
    }

    freeaddrinfo(res);

    if (ok) {
        ESP_LOGI(TAG, "%s probe OK | %s:%u", label ? label : "tcp", host, (unsigned)port);
    } else {
        ESP_LOGW(TAG, "%s probe failed | %s:%u", label ? label : "tcp", host, (unsigned)port);
    }

    return ok;
}

static bool http_probe_url(const char *url, int timeout_ms, const char *label, int *out_status)
{
    if (out_status) {
        *out_status = 0;
    }

    esp_http_client_config_t http_cfg = {
        .url = url,
        .method = HTTP_METHOD_GET,
        .timeout_ms = timeout_ms,
    };
    if (url && strncmp(url, "https", 5) == 0) {
        http_cfg.crt_bundle_attach = esp_crt_bundle_attach;
    }

    esp_http_client_handle_t client = esp_http_client_init(&http_cfg);
    if (!client) {
        ESP_LOGW(TAG, "%s probe: cannot create HTTP client", label ? label : "http");
        return false;
    }

    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (out_status) {
        *out_status = status;
    }

    if (err != ESP_OK) {
        ESP_LOGW(
            TAG,
            "%s probe failed | url=%s err=%s",
            label ? label : "http",
            url ? url : "-",
            esp_err_to_name(err)
        );
        return false;
    }

    if (status == 200 || status == 204) {
        ESP_LOGI(TAG, "%s probe OK | url=%s http=%d", label ? label : "http", url, status);
        return true;
    }

    ESP_LOGW(TAG, "%s probe unexpected status | url=%s http=%d", label ? label : "http", url, status);
    return false;
}

static const char *wifi_reason_to_text(int reason)
{
    switch (reason) {
        case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT:
            return "timeout bat tay WPA";
        case WIFI_REASON_AUTH_FAIL:
            return "xac thuc that bai";
        case WIFI_REASON_HANDSHAKE_TIMEOUT:
            return "timeout handshake";
        case WIFI_REASON_CONNECTION_FAIL:
            return "router tu choi ket noi";
        case WIFI_REASON_NO_AP_FOUND:
            return "khong tim thay access point";
        case WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD:
            return "khong tim thay AP phu hop che do bao mat";
        default:
            return "ly do khong xac dinh";
    }
}

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

static bool parse_wifi_form(
    char *body,
    char *ssid,
    size_t ssid_len,
    char *password,
    size_t pass_len,
    char *location,
    size_t loc_len
)
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
        } else if (strcmp(key, "location") == 0) {
            snprintf(location, loc_len, "%s", value);
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

static void optimize_wifi_for_streaming(wifi_mode_t mode)
{
    esp_err_t err = esp_wifi_set_ps(WIFI_PS_NONE);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Cannot disable WiFi power save: %s", esp_err_to_name(err));
    }

    if (mode == WIFI_MODE_STA || mode == WIFI_MODE_APSTA) {
        err = esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT40);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Cannot set STA HT40 bandwidth: %s", esp_err_to_name(err));
        }
    }

    if (mode == WIFI_MODE_AP || mode == WIFI_MODE_APSTA) {
        err = esp_wifi_set_bandwidth(WIFI_IF_AP, WIFI_BW_HT40);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Cannot set AP HT40 bandwidth: %s", esp_err_to_name(err));
        }
    }
}

static esp_err_t get_ap_ip_info(esp_netif_ip_info_t *out_ip, char *ip_str, size_t ip_str_len)
{
    if (!s_ap_netif || !out_ip) {
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t err = esp_netif_get_ip_info(s_ap_netif, out_ip);
    if (err != ESP_OK) {
        return err;
    }

    if (ip_str && ip_str_len > 0) {
        inet_ntoa_r(out_ip->ip.addr, ip_str, ip_str_len);
    }

    return ESP_OK;
}

static bool wifi_verify_sta_link(const char *ssid)
{
    if (!s_sta_netif) {
        ESP_LOGW(TAG, "WiFi check: STA netif not ready");
        return false;
    }

    vTaskDelay(pdMS_TO_TICKS(WIFI_STA_VERIFY_STABLE_MS));

    if (!s_sta_connected) {
        ESP_LOGW(TAG, "WiFi check: link dropped before verify");
        return false;
    }

    esp_netif_ip_info_t ip_info = {0};
    if (esp_netif_get_ip_info(s_sta_netif, &ip_info) != ESP_OK ||
        ip_info.ip.addr == 0 ||
        ip_info.gw.addr == 0) {
        ESP_LOGW(TAG, "WiFi check: missing IP or gateway");
        return false;
    }

    char ip_str[16] = {0};
    snprintf(ip_str, sizeof(ip_str), IPSTR, IP2STR(&ip_info.ip));

    bool mqtt_ok = tcp_probe_uri(MQTT_BROKER_URI, WIFI_VERIFY_TIMEOUT_MS, "MQTT");
    if (mqtt_ok) {
        ESP_LOGI(TAG, "WiFi OK | ssid=%s ip=%s verify=mqtt", ssid ? ssid : "-", ip_str);
        return true;
    }

    int http_status = 0;
    bool http_ok = http_probe_url(WIFI_VERIFY_URL, WIFI_VERIFY_TIMEOUT_MS, WIFI_VERIFY_LABEL, &http_status);
    if (http_ok) {
        ESP_LOGI(
            TAG,
            "WiFi OK | ssid=%s ip=%s verify=%s(%d)",
            ssid ? ssid : "-",
            ip_str,
            WIFI_VERIFY_LABEL,
            http_status
        );
        return true;
    }

    ESP_LOGW(
        TAG,
        "WiFi LAN OK but service probes failed | ssid=%s ip=%s mqtt=%s %s_url=%s",
        ssid ? ssid : "-",
        ip_str,
        MQTT_BROKER_URI,
        WIFI_VERIFY_LABEL,
        WIFI_VERIFY_URL
    );
    return true;
}

static const char *get_captive_portal_uri(void)
{
    if (s_captive_portal_uri[0]) {
        return s_captive_portal_uri;
    }

    return "http://192.168.4.1";
}

static esp_err_t configure_captive_portal_dhcp(void)
{
    esp_netif_ip_info_t ap_ip = {0};
    char ap_ip_str[16] = "192.168.4.1";
    ESP_RETURN_ON_ERROR(get_ap_ip_info(&ap_ip, ap_ip_str, sizeof(ap_ip_str)), TAG, "Khong doc duoc IP SoftAP");

    esp_netif_dns_info_t dns = {0};
    dns.ip.type = ESP_IPADDR_TYPE_V4;
    dns.ip.u_addr.ip4 = ap_ip.ip;

    snprintf(s_captive_portal_uri, sizeof(s_captive_portal_uri), "http://%s", ap_ip_str);

    ESP_RETURN_ON_ERROR(esp_netif_dhcps_stop(s_ap_netif), TAG, "Khong dung duoc DHCP server cua SoftAP");

    uint8_t dhcps_offer_dns = DHCPS_OFFER_DNS;
    esp_err_t err = esp_netif_dhcps_option(
        s_ap_netif,
        ESP_NETIF_OP_SET,
        ESP_NETIF_DOMAIN_NAME_SERVER,
        &dhcps_offer_dns,
        sizeof(dhcps_offer_dns)
    );
    if (err != ESP_OK) {
        esp_netif_dhcps_start(s_ap_netif);
        return err;
    }

    err = esp_netif_set_dns_info(s_ap_netif, ESP_NETIF_DNS_MAIN, &dns);
    if (err != ESP_OK) {
        esp_netif_dhcps_start(s_ap_netif);
        return err;
    }

    err = esp_netif_dhcps_option(
        s_ap_netif,
        ESP_NETIF_OP_SET,
        ESP_NETIF_CAPTIVEPORTAL_URI,
        s_captive_portal_uri,
        strlen(s_captive_portal_uri)
    );
    if (err != ESP_OK) {
        esp_netif_dhcps_start(s_ap_netif);
        return err;
    }

    return esp_netif_dhcps_start(s_ap_netif);
}

static esp_err_t start_captive_portal_dns(void)
{
    if (s_dns_server) {
        return ESP_OK;
    }

    dns_server_config_t config = DNS_SERVER_CONFIG_SINGLE("*", "WIFI_AP_DEF");
    s_dns_server = start_dns_server(&config);
    if (!s_dns_server) {
        return ESP_FAIL;
    }

    return ESP_OK;
}

static void stop_captive_portal_dns(void)
{
    if (!s_dns_server) {
        return;
    }

    stop_dns_server(s_dns_server);
    s_dns_server = NULL;
}



static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *event = (wifi_event_sta_disconnected_t *)data;
        s_last_disconnect_reason = event ? (int)event->reason : -1;
        s_sta_connected = false;
        g_wifi_disconnect_count++; /* Tang so lan mat ket noi WiFi */
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
        set_status_message("📶 Đã kết nối WiFi, IP: " IPSTR, IP2STR(&event->ip_info.ip));
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
        ESP_LOGE(TAG, "❌ Không khởi tạo được tài nguyên WiFi Manager");
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
    s_portal_restart_pending = false;

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
    optimize_wifi_for_streaming(WIFI_MODE_APSTA);
    ESP_ERROR_CHECK(configure_captive_portal_dhcp());
    ESP_ERROR_CHECK(start_captive_portal_dns());

    s_portal_active = true;
    esp_netif_ip_info_t ap_ip = {0};
    const bool has_ap_ip = s_ap_netif && esp_netif_get_ip_info(s_ap_netif, &ap_ip) == ESP_OK;
    char ap_ip_str[16] = "192.168.4.1";
    if (has_ap_ip) {
        snprintf(ap_ip_str, sizeof(ap_ip_str), IPSTR, IP2STR(&ap_ip.ip));
    }
    if (ap_pass_len >= 8) {
        set_status_message("🌐 AP %s đã bật. Truy cập %s để cấu hình", WIFI_MANAGER_AP_SSID, ap_ip_str);
        ESP_LOGW(
            TAG,
            "🌐 Bật SoftAP cấu hình: SSID=%s, truy cập http://%s/",
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
    stop_captive_portal_dns();

    if (s_portal_httpd) {
        httpd_stop(s_portal_httpd);
        s_portal_httpd = NULL;
    }

    s_portal_active = false;
    s_captive_portal_uri[0] = '\0';
    esp_err_t err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "⚠️ Không chuyển được sang STA-only: %s", esp_err_to_name(err));
    }
}

static bool wifi_connect_sta(const char *ssid, const char *password, int max_retry, bool keep_ap_active)
{
    if (!ssid || ssid[0] == '\0') {
        ESP_LOGW(TAG, "⚠️ Chưa có cấu hình SSID để kết nối");
        return false;
    }

    wifi_config_t sta_cfg = {0};
    snprintf((char *)sta_cfg.sta.ssid, sizeof(sta_cfg.sta.ssid), "%s", ssid);
    snprintf((char *)sta_cfg.sta.password, sizeof(sta_cfg.sta.password), "%s", password ? password : "");
    sta_cfg.sta.threshold.authmode = WIFI_AUTH_OPEN;
    sta_cfg.sta.pmf_cfg.capable = true;
    sta_cfg.sta.pmf_cfg.required = false;

    xEventGroupClearBits(s_evt_group, WIFI_CONNECTED_BIT | WIFI_DISCONNECTED_BIT);

    ESP_LOGI(TAG, "📡 Đang cấu hình kết nối WiFi: %s", ssid);
    ESP_ERROR_CHECK(esp_wifi_set_mode(keep_ap_active ? WIFI_MODE_APSTA : WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta_cfg));
    ESP_ERROR_CHECK(configure_sta_static_ip());
    ESP_ERROR_CHECK(wifi_start_or_reuse());
    optimize_wifi_for_streaming(keep_ap_active ? WIFI_MODE_APSTA : WIFI_MODE_STA);

    set_status_message("📡 Đang thử kết nối WiFi: %s", ssid);

    for (int attempt = 1; attempt <= max_retry; ++attempt) {
        ESP_LOGI(TAG, "📡 Thử kết nối lần %d/%d...", attempt, max_retry);
        set_status_message("📡 Đang kết nối WiFi... (lần %d/%d)", attempt, max_retry);
        
        xEventGroupClearBits(s_evt_group, WIFI_CONNECTED_BIT | WIFI_DISCONNECTED_BIT);
        esp_err_t err = esp_wifi_connect();
        if (err != ESP_OK && err != ESP_ERR_WIFI_CONN) {
            ESP_LOGW(TAG, "⚠️ Lỗi esp_wifi_connect: %s", esp_err_to_name(err));
        }

        EventBits_t bits = xEventGroupWaitBits(
            s_evt_group,
            WIFI_CONNECTED_BIT | WIFI_DISCONNECTED_BIT,
            pdTRUE,
            pdFALSE,
            pdMS_TO_TICKS(10000) // Tăng timeout lên 10s cho chắc
        );

        if (bits & WIFI_CONNECTED_BIT) {
            ESP_LOGI(TAG, "✅ WiFi đã kết nối thành công: %s", ssid);
            set_status_message("✅ Đã kết nối WiFi: %s", ssid);
            return true;
        }

        ESP_LOGW(TAG, "❌ Thử lần %d/%d thất bại (reason=%d)", attempt, max_retry, s_last_disconnect_reason);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }

    ESP_LOGE(TAG, "❌ Không thể kết nối SSID \"%s\" sau %d lần thử", ssid, max_retry);
    set_status_message("❌ Lỗi kết nối WiFi: %s", ssid);
    return false;
}

static esp_err_t portal_root_handler(httpd_req_t *req)
{
    char saved_ssid[33];
    char saved_loc[65];
    get_status_snapshot(NULL, 0, saved_ssid, sizeof(saved_ssid), NULL, NULL);

    if (s_state_mutex) xSemaphoreTake(s_state_mutex, portMAX_DELAY);
    saved_loc[0] = '\0';
    if (s_active_cfg) {
        // Kiểm tra xem location có chứa ký tự không in được không (lỗi ␅)
        bool valid = true;
        for (int i = 0; s_active_cfg->location[i]; i++) {
            if ((unsigned char)s_active_cfg->location[i] < 32 && (unsigned char)s_active_cfg->location[i] != '\n') {
                valid = false;
                break;
            }
        }
        if (valid && s_active_cfg->location[0]) {
            snprintf(saved_loc, sizeof(saved_loc), "%s", s_active_cfg->location);
        }
    }
    if (s_state_mutex) xSemaphoreGive(s_state_mutex);

    char html[4096];
    int len = snprintf(
        html,
        sizeof(html),
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>WiFi Setup</title>"
        "<style>"
        "body{font-family:system-ui,-apple-system,sans-serif;background:#0b1220;color:#e5edf7;margin:0;padding:20px;display:flex;justify-content:center;align-items:start;min-height:100vh}"
        ".card{width:100%%;max-width:400px;background:#14213d;border:1px solid #243b68;border-radius:18px;padding:20px;box-shadow:0 10px 25px rgba(0,0,0,0.3)}"
        "h1{margin:0 0 16px;font-size:24px;text-align:center;color:#f6c445}"
        "label{display:block;margin:12px 0 4px;font-weight:600;font-size:14px;color:#b8c5db}"
        "input,select,button{width:100%%;padding:10px 12px;border-radius:10px;border:1px solid #33538b;font-size:15px;box-sizing:border-box}"
        "input,select{background:#0e1a30;color:#fff}button{background:#f6c445;color:#171717;font-weight:700;cursor:pointer;margin-top:16px;border:none}"
        ".row{display:grid;grid-template-columns:1fr auto;gap:8px;margin-bottom:12px}"
        ".row button{margin-top:0;padding:8px 16px;width:auto}"
        ".hint{font-size:12px;color:#8899af;text-align:center;margin-top:16px}"
        "#status{padding:10px;border-radius:10px;background:#0e1a30;border:1px solid #233659;margin-bottom:16px;font-weight:600;text-align:center;font-size:14px}"
        "</style></head><body><div class='card'>"
        "<h1>WiFi Setup</h1>"
        "<div id='status'>Đang chờ lệnh...</div>"
        "<div class='row'><select id='scanList'><option value=''>Chọn WiFi...</option></select>"
        "<button type='button' id='scanBtn'>Quét</button></div>"
        "<form id='wifiForm'>"
        "<label for='ssid'>SSID</label>"
        "<input id='ssid' name='ssid' maxlength='32' value='%s' placeholder='Tên WiFi' required>"
        "<label for='password'>Mật khẩu</label>"
        "<input id='password' name='password' maxlength='64' type='password' placeholder='Mật khẩu (nếu có)'>"
        "<label for='location'>Vị trí lắp đặt</label>"
        "<input id='location' name='location' maxlength='64' value='%s' placeholder='Ví dụ: Kho A'>"
        "<button type='submit'>Lưu và kết nối</button></form>"
        "<p class='hint'>Thiết bị sẽ tự khởi động lại sau khi lưu.</p></div>"
        "<script>"
        "const statusEl=document.getElementById('status');"
        "const scanList=document.getElementById('scanList');"
        "document.getElementById('scanBtn').onclick=async()=>{"
        "statusEl.textContent='Đang quét WiFi...';statusEl.style.color='#f6c445';"
        "try{const r=await fetch('/api/wifi/scan');const d=await r.json();"
        "if(!r.ok)throw new Error(d.detail);"
        "scanList.innerHTML=\"<option value=''>Chọn WiFi...</option>\";"
        "for(const ssid of d.ssids||[]){const o=document.createElement('option');o.value=ssid;o.textContent=ssid;scanList.appendChild(o);}"
        "statusEl.textContent='Quét xong!';statusEl.style.color='#4ade80';}"
        "catch(e){statusEl.textContent='Lỗi: '+e.message;statusEl.style.color='#f87171';}};"
        "scanList.onchange=()=>{if(scanList.value)document.getElementById('ssid').value=scanList.value;};"
        "async function refreshStatus(){try{const r=await fetch('/api/wifi/status');const d=await r.json();"
        "if(d.connected){statusEl.textContent='✅ '+d.ssid;statusEl.style.color='#4ade80';}"
        "else if(d.status)statusEl.textContent=d.status;}catch(e){}}"
        "setInterval(refreshStatus,4000);refreshStatus();"
        "document.getElementById('wifiForm').onsubmit=async(e)=>{e.preventDefault();"
        "statusEl.textContent='Đang lưu...';statusEl.style.color='#f6c445';"
        "const form=new URLSearchParams(new FormData(e.target));"
        "try{const r=await fetch('/api/wifi/save',{method:'POST',body:form});"
        "const d=await r.json();statusEl.textContent=d.message||d.detail;"
        "if(r.ok)statusEl.style.color='#4ade80';else statusEl.style.color='#f87171';}"
        "catch(err){statusEl.textContent='Lỗi kết nối';statusEl.style.color='#f87171';}};"
        "</script></body></html>",
        saved_ssid,
        saved_loc
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
    ESP_LOGI(TAG, "🔍 Đang bắt đầu quét WiFi...");
    wifi_scan_config_t scan_cfg = {0};
    
    // Nếu Station đang cố kết nối, việc quét có thể thất bại.
    // Thử dừng các tiến trình khác nếu cần, nhưng thông thường APSTA cho phép quét.
    esp_err_t err = esp_wifi_scan_start(&scan_cfg, true);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "❌ Lỗi esp_wifi_scan_start: %s", esp_err_to_name(err));
        httpd_resp_set_status(req, "503 Service Unavailable");
        httpd_resp_set_type(req, "application/json");
        char err_msg[128];
        snprintf(err_msg, sizeof(err_msg), "{\"detail\":\"Lỗi quét WiFi: %s\"}", esp_err_to_name(err));
        return httpd_resp_sendstr(req, err_msg);
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
    char location[65];
    location[0] = '\0';

    if (!parse_wifi_form(body, ssid, sizeof(ssid), password, sizeof(password), location, sizeof(location))) {
        httpd_resp_set_status(req, "400 Bad Request");
        httpd_resp_set_type(req, "application/json");
        return httpd_resp_sendstr(req, "{\"detail\":\"SSID không được để trống\"}");
    }

    app_config_t candidate_cfg = *s_active_cfg;

    snprintf(candidate_cfg.ssid, sizeof(candidate_cfg.ssid), "%s", ssid);
    snprintf(candidate_cfg.password, sizeof(candidate_cfg.password), "%s", password);
    if (location[0]) {
        snprintf(candidate_cfg.location, sizeof(candidate_cfg.location), "%s", location);
    }

    set_status_message("Đang thử kết nối WiFi %s...", candidate_cfg.ssid);

    if (!wifi_connect_sta(
            candidate_cfg.ssid,
            candidate_cfg.password,
            WIFI_PORTAL_CONNECT_RETRY,
            true)) {
        esp_err_t disconnect_err = esp_wifi_disconnect();
        if (disconnect_err != ESP_OK && disconnect_err != ESP_ERR_WIFI_NOT_CONNECT) {
            ESP_LOGW(TAG, "esp_wifi_disconnect sau khi thu portal that bai: %s", esp_err_to_name(disconnect_err));
        }

        char response[256];
        snprintf(
            response,
            sizeof(response),
            "{\"success\":false,\"detail\":\"Khong ket noi duoc WiFi '%s' (%s, reason=%d). Portal van mo de ban thu lai.\"}",
            candidate_cfg.ssid,
            wifi_reason_to_text(s_last_disconnect_reason),
            s_last_disconnect_reason
        );

        set_status_message(
            "Không kết nối được %s (%s, reason=%d). Portal vẫn sẵn sàng.",
            candidate_cfg.ssid,
            wifi_reason_to_text(s_last_disconnect_reason),
            s_last_disconnect_reason
        );

        httpd_resp_set_status(req, "400 Bad Request");
        httpd_resp_set_type(req, "application/json");
        httpd_resp_set_hdr(req, "Cache-Control", "no-store");
        return httpd_resp_sendstr(req, response);
    }

    if (!wifi_verify_sta_link(candidate_cfg.ssid)) {
        set_status_message(
            "WiFi %s chua on dinh hoac chua lay du IP/gateway. Portal van mo de thu lai.",
            candidate_cfg.ssid
        );
        httpd_resp_set_status(req, "400 Bad Request");
        httpd_resp_set_type(req, "application/json");
        httpd_resp_set_hdr(req, "Cache-Control", "no-store");
        return httpd_resp_sendstr(
            req,
            "{\"success\":false,\"detail\":\"WiFi chua on dinh hoac chua lay du IP/gateway. Portal van mo de ban thu lai.\"}"
        );
    }

    *s_active_cfg = candidate_cfg;
    if (app_config_save(s_active_cfg) != ESP_OK) {
        set_status_message("Đã kết nối WiFi nhưng lưu NVS thất bại. Portal vẫn mở để thử lại.");
        httpd_resp_set_status(req, "500 Internal Server Error");
        httpd_resp_set_type(req, "application/json");
        httpd_resp_set_hdr(req, "Cache-Control", "no-store");
        return httpd_resp_sendstr(
            req,
            "{\"detail\":\"Da ket noi WiFi nhung khong luu duoc vao NVS. Chua reboot.\"}"
        );
    }

    set_status_message("WiFi hợp lệ. Đã lưu cấu hình, đang khởi động lại...");
    xEventGroupSetBits(s_evt_group, WIFI_PORTAL_SUBMIT_BIT);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(
        req,
        "{\"success\":true,\"message\":\"Ket noi WiFi thanh cong. Da luu vao flash, ESP32 dang khoi dong lai...\"}"
    );
}

static esp_err_t portal_redirect_handler(httpd_req_t *req)
{
    httpd_resp_set_status(req, "302 Temporary Redirect");
    httpd_resp_set_hdr(req, "Location", get_captive_portal_uri());
    httpd_resp_set_type(req, "text/plain");
    return httpd_resp_sendstr(req, "Redirect to the ESP32 captive portal");
}

static esp_err_t portal_not_found_handler(httpd_req_t *req, httpd_err_code_t err)
{
    (void)err;
    return portal_redirect_handler(req);
}

static esp_err_t start_portal_server(void)
{
    if (s_portal_httpd) {
        return ESP_OK;
    }

    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.max_uri_handlers = 10;
    config.max_open_sockets = 4;
    config.lru_purge_enable = true;
    config.stack_size = 8192;

    esp_err_t err = httpd_start(&s_portal_httpd, &config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "❌ Không khởi động được WiFi Portal: %s", esp_err_to_name(err));
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
    httpd_uri_t android_204_uri = {
        .uri = "/generate_204",
        .method = HTTP_GET,
        .handler = portal_redirect_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t android_redirect_uri = {
        .uri = "/redirect",
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
    httpd_uri_t connectivity_uri = {
        .uri = "/connectivity-check.html",
        .method = HTTP_GET,
        .handler = portal_redirect_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t ncsi_uri = {
        .uri = "/ncsi.txt",
        .method = HTTP_GET,
        .handler = portal_redirect_handler,
        .user_ctx = NULL,
    };

    httpd_register_uri_handler(s_portal_httpd, &root_uri);
    httpd_register_uri_handler(s_portal_httpd, &status_uri);
    httpd_register_uri_handler(s_portal_httpd, &scan_uri);
    httpd_register_uri_handler(s_portal_httpd, &save_uri);
    httpd_register_uri_handler(s_portal_httpd, &android_204_uri);
    httpd_register_uri_handler(s_portal_httpd, &android_redirect_uri);
    httpd_register_uri_handler(s_portal_httpd, &apple_uri);
    httpd_register_uri_handler(s_portal_httpd, &connectivity_uri);
    httpd_register_uri_handler(s_portal_httpd, &ncsi_uri);
    httpd_register_err_handler(s_portal_httpd, HTTPD_404_NOT_FOUND, portal_not_found_handler);

    ESP_LOGI(TAG, "🌐 WiFi portal đã sẵn sàng tại %s/", get_captive_portal_uri());
    return ESP_OK;
}

static bool run_config_portal_until_connected(app_config_t *cfg, int max_retry)
{
    (void)max_retry;

    if (start_config_ap() != ESP_OK || start_portal_server() != ESP_OK) {
        return false;
    }

    if (cfg->ssid[0]) {
        set_status_message(
            "Portal cấu hình đang bật. WiFi hiện tại là %s, mở 192.168.4.1 để đổi",
            cfg->ssid
        );
    } else {
        set_status_message("Đang chờ cấu hình WiFi qua AP %s", WIFI_MANAGER_AP_SSID);
    }

    while (true) {
        xEventGroupWaitBits(
            s_evt_group,
            WIFI_PORTAL_SUBMIT_BIT,
            pdTRUE,
            pdFALSE,
            portMAX_DELAY
        );

        if (cfg->ssid[0]) {
            ESP_LOGW(TAG, "🔄 Hệ thống sẽ khởi động lại sau 500ms...");
            vTaskDelay(pdMS_TO_TICKS(500)); 
            stop_config_ap();
            esp_restart();
        }
    }
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

    if (WIFI_FORCE_PORTAL_ON_BOOT) {
        ESP_LOGW(TAG, "⚙️ Bật chế độ ép mở WiFi config portal khi boot");
        return run_config_portal_until_connected(cfg, max_retry);
    }

    if (cfg->ssid[0] && wifi_connect_sta(cfg->ssid, cfg->password, max_retry, false)) {
        return true;
    }

    return run_config_portal_until_connected(cfg, max_retry);
}

bool wifi_manager_verify_connected_sta(void)
{
    const char *ssid = NULL;
    if (s_active_cfg && s_active_cfg->ssid[0]) {
        ssid = s_active_cfg->ssid;
    }
    return wifi_verify_sta_link(ssid);
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
