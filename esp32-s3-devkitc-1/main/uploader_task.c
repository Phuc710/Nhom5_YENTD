/*
 * uploader_task.c - Upload frame len backend HTTP va MinIO/S3
 *
 * Telemetry export (doc boi health_task):
 *   g_last_upload_ok
 *   g_last_http_code
 *   g_last_latency_ms
 */
#include "task_manager.h"
#include "uploader_task.h"
#include "led_status.h"
#include "traffic_light.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "mbedtls/md.h"
#include "mbedtls/sha256.h"
#include <stdlib.h>
#include <string.h>
#include <time.h>

static const char *TAG = "uploader";

volatile bool     g_last_upload_ok  = false;
volatile int      g_last_http_code  = 0;
volatile uint32_t g_last_latency_ms = 0;

/* MinIO/S3 config */
#ifndef MINIO_ENDPOINT
#define MINIO_ENDPOINT   ""
#endif
#ifndef MINIO_ACCESS_KEY
#define MINIO_ACCESS_KEY ""
#endif
#ifndef MINIO_SECRET_KEY
#define MINIO_SECRET_KEY ""
#endif
#ifndef MINIO_BUCKET
#define MINIO_BUCKET     "cam"
#endif
#ifndef MINIO_REGION
#define MINIO_REGION     "us-east-1"
#endif
#ifndef MINIO_USE_TLS
#define MINIO_USE_TLS    0
#endif

#define HEARTBEAT_INTERVAL_US 5000000LL

static char s_endpoint[128]   = MINIO_ENDPOINT;
static char s_access_key[96]  = MINIO_ACCESS_KEY;
static char s_secret_key[96]  = MINIO_SECRET_KEY;
static char s_bucket[64]      = MINIO_BUCKET;
static char s_region[32]      = MINIO_REGION;
static bool s_use_tls         = (MINIO_USE_TLS != 0);

static uint32_t s_minio_sent      = 0;
static uint32_t s_minio_index     = 0;
static uint32_t s_epoch_seen      = 0;
static bool     s_limit_logged    = false;

/* Backend server */
#ifndef BACKEND_UPLOAD_URL
#  error "BACKEND_UPLOAD_URL chua duoc dinh nghia! Them vao platformio.ini build_flags."
#endif

static char s_server[128] = BACKEND_UPLOAD_URL;
static char s_token[128]  = {0};
static bool s_has_token   = false;

static int  s_fail_streak     = 0;
static bool s_led_err_toggle  = false;

static void build_backend_url(char *out, size_t out_len, const char *path);
static bool send_form_post(const char *path, const char *form_body);
static bool send_finalize(int camera_id);
static bool send_heartbeat(int camera_id);
static void apply_pending_capture_interval(void);

/* ---- Public setters ---- */

void uploader_set_token(const char *tok) {
    if (tok && tok[0]) {
        strncpy(s_token, tok, sizeof(s_token) - 1);
        s_has_token = true;
    }
}

void uploader_set_server(const char *host, int cam_id) {
    if (host && host[0]) strncpy(s_server, host, sizeof(s_server) - 1);
    g_camera_id = cam_id;
}

void uploader_set_minio_config(const char *ep, const char *ak,
                               const char *sk, const char *bucket,
                               const char *region, int use_tls) {
    if (ep)     { ep[0]     ? strncpy(s_endpoint, ep, sizeof(s_endpoint) - 1)         : (void)(s_endpoint[0] = 0); }
    if (ak)     { ak[0]     ? strncpy(s_access_key, ak, sizeof(s_access_key) - 1)     : (void)(s_access_key[0] = 0); }
    if (sk)     { sk[0]     ? strncpy(s_secret_key, sk, sizeof(s_secret_key) - 1)     : (void)(s_secret_key[0] = 0); }
    if (bucket) { bucket[0] ? strncpy(s_bucket, bucket, sizeof(s_bucket) - 1)         : (void)(s_bucket[0] = 0); }
    if (region) { region[0] ? strncpy(s_region, region, sizeof(s_region) - 1)         : (void)(s_region[0] = 0); }
    if (use_tls >= 0) s_use_tls = (use_tls != 0);
    if (!s_bucket[0]) strncpy(s_bucket, "cam", sizeof(s_bucket) - 1);
    if (!s_region[0]) strncpy(s_region, "us-east-1", sizeof(s_region) - 1);
    s_minio_sent = s_minio_index = 0;
    s_limit_logged = false;
    ESP_LOGI(TAG, "MinIO: %s/%s (TLS=%s)", s_endpoint, s_bucket,
             s_use_tls ? "bat" : "tat");
}

/* ---- Crypto helpers ---- */

static void hex_encode(const uint8_t *in, size_t len, char *out) {
    static const char h[] = "0123456789abcdef";
    for (size_t i = 0; i < len; i++) {
        out[i * 2] = h[in[i] >> 4];
        out[i * 2 + 1] = h[in[i] & 0xF];
    }
    out[len * 2] = '\0';
}

static bool sha256_hex(const uint8_t *d, size_t l, char *out) {
    uint8_t hash[32];
    if (mbedtls_sha256(d, l, hash, 0) != 0) return false;
    hex_encode(hash, 32, out);
    return true;
}

static bool hmac_sha256(const uint8_t *key, size_t kl,
                        const uint8_t *msg, size_t ml, uint8_t out[32]) {
    mbedtls_md_context_t ctx;
    const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (!info) return false;
    mbedtls_md_init(&ctx);
    bool ok = (mbedtls_md_setup(&ctx, info, 1) == 0 &&
               mbedtls_md_hmac_starts(&ctx, key, kl) == 0 &&
               mbedtls_md_hmac_update(&ctx, msg, ml) == 0 &&
               mbedtls_md_hmac_finish(&ctx, out) == 0);
    mbedtls_md_free(&ctx);
    return ok;
}

/* ---- HTTP backend upload ---- */

static bool send_http(const frame_msg_t *frame)
{
    static const char *BOUNDARY = "----EspCamBndry";
    const char *traffic_state = (frame->traffic_state == TL_STATE_RED) ? "red" :
                                (frame->traffic_state == TL_STATE_YELLOW) ? "yellow" : "green";
    const char *operation_mode = (frame->operation_mode == TL_MODE_NORMAL) ? "normal" :
                                 (frame->operation_mode == TL_MODE_EMERGENCY_RED) ? "emergency_red" :
                                                                                   "emergency_green";

    char url[280];
    build_backend_url(url, sizeof(url), "/api/upload");

    char part_cam[128];
    char part_state[160];
    char part_mode[176];
    char part_state_ms[160];
    char part_file[160];
    char part_end[32];

    int part_cam_len = snprintf(
        part_cam, sizeof(part_cam),
        "--%s\r\nContent-Disposition: form-data; name=\"camera_id\"\r\n\r\n%d\r\n",
        BOUNDARY, frame->camera_id
    );
    int part_state_len = snprintf(
        part_state, sizeof(part_state),
        "--%s\r\nContent-Disposition: form-data; name=\"traffic_light_state\"\r\n\r\n%s\r\n",
        BOUNDARY, traffic_state
    );
    int part_mode_len = snprintf(
        part_mode, sizeof(part_mode),
        "--%s\r\nContent-Disposition: form-data; name=\"operation_mode\"\r\n\r\n%s\r\n",
        BOUNDARY, operation_mode
    );
    int part_state_ms_len = snprintf(
        part_state_ms, sizeof(part_state_ms),
        "--%s\r\nContent-Disposition: form-data; name=\"tl_state_ms\"\r\n\r\n%lu\r\n",
        BOUNDARY, (unsigned long)frame->tl_state_ms
    );
    int part_file_len = snprintf(
        part_file, sizeof(part_file),
        "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"img.jpg\"\r\n"
        "Content-Type: image/jpeg\r\n\r\n",
        BOUNDARY
    );
    int part_end_len = snprintf(part_end, sizeof(part_end), "\r\n--%s--\r\n", BOUNDARY);
    if (part_cam_len < 0 || part_state_len < 0 || part_mode_len < 0 ||
        part_state_ms_len < 0 || part_file_len < 0 || part_end_len < 0) return false;

    size_t total = (size_t)part_cam_len + (size_t)part_state_len +
                   (size_t)part_mode_len + (size_t)part_state_ms_len +
                   (size_t)part_file_len + frame->len + (size_t)part_end_len;
    char *body = malloc(total + 1);
    if (!body) { ESP_LOGE(TAG, "Không đủ RAM cho body"); return false; }

    size_t offset = 0;
    memcpy(body + offset, part_cam, (size_t)part_cam_len); offset += (size_t)part_cam_len;
    memcpy(body + offset, part_state, (size_t)part_state_len); offset += (size_t)part_state_len;
    memcpy(body + offset, part_mode, (size_t)part_mode_len); offset += (size_t)part_mode_len;
    memcpy(body + offset, part_state_ms, (size_t)part_state_ms_len); offset += (size_t)part_state_ms_len;
    memcpy(body + offset, part_file, (size_t)part_file_len); offset += (size_t)part_file_len;
    memcpy(body + offset, frame->data, frame->len); offset += frame->len;
    memcpy(body + offset, part_end, (size_t)part_end_len); offset += (size_t)part_end_len;
    body[offset] = '\0';

    esp_http_client_config_t cfg = {
        .url    = url,
        .method = HTTP_METHOD_POST,
    };
    if (strncmp(url, "https", 5) == 0) {
        cfg.crt_bundle_attach = esp_crt_bundle_attach;
    }
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) { free(body); return false; }

    char ctype[80];
    snprintf(ctype, sizeof(ctype), "multipart/form-data; boundary=%s", BOUNDARY);
    esp_http_client_set_header(client, "Content-Type", ctype);
    if (s_has_token) {
        char auth[160];
        snprintf(auth, sizeof(auth), "Bearer %s", s_token);
        esp_http_client_set_header(client, "Authorization", auth);
    }
    esp_http_client_set_post_field(client, body, (int)total);

    int64_t t0 = esp_timer_get_time();
    esp_err_t err = esp_http_client_perform(client);
    int64_t t1 = esp_timer_get_time();

    int code = esp_http_client_get_status_code(client);
    bool ok = (err == ESP_OK && code >= 200 && code < 300);
    uint32_t lat = (uint32_t)((t1 - t0) / 1000LL);

    g_last_upload_ok = ok;
    g_last_http_code = code;
    g_last_latency_ms = lat;

    if (ok) {
        ESP_LOGI(TAG, "Tải lên thành công seq=%lu %u bytes HTTP=%d %lums",
                 (unsigned long)frame->sequence, (unsigned)frame->len,
                 code, (unsigned long)lat);
    } else {
        ESP_LOGE(TAG, "Upload thất bại HTTP=%d err=%s", code, esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    free(body);
    return ok;
}

static bool send_form_post(const char *path, const char *form_body)
{
    char url[280];
    build_backend_url(url, sizeof(url), path);

    esp_http_client_config_t cfg = {
        .url    = url,
        .method = HTTP_METHOD_POST,
    };
    if (strncmp(url, "https", 5) == 0) {
        cfg.crt_bundle_attach = esp_crt_bundle_attach;
    }
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return false;

    esp_http_client_set_header(client, "Content-Type", "application/x-www-form-urlencoded");
    if (s_has_token) {
        char auth[160];
        snprintf(auth, sizeof(auth), "Bearer %s", s_token);
        esp_http_client_set_header(client, "Authorization", auth);
    }
    esp_http_client_set_post_field(client, form_body, (int)strlen(form_body));

    esp_err_t err = esp_http_client_perform(client);
    int code = esp_http_client_get_status_code(client);
    bool ok = (err == ESP_OK && code >= 200 && code < 300);
    if (!ok) {
        ESP_LOGW(TAG, "POST %s thất bại code=%d err=%s", path, code, esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    return ok;
}

static bool send_finalize(int camera_id)
{
    char form[64];
    snprintf(form, sizeof(form), "camera_id=%d", camera_id);
    return send_form_post("/api/finalize", form);
}

static bool send_heartbeat(int camera_id)
{
    char form[64];
    snprintf(form, sizeof(form), "camera_id=%d", camera_id);
    return send_form_post("/api/upload/heartbeat", form);
}

/* ---- MinIO S3 signed upload ---- */

static bool send_minio(const frame_msg_t *frame)
{
    if (!s_endpoint[0] || !s_access_key[0] || !s_secret_key[0]) return false;

    time_t now = 0;
    time(&now);
    struct tm utc = {0};
    gmtime_r(&now, &utc);
    if (utc.tm_year + 1900 < 2020) {
        ESP_LOGE(TAG, "Đồng hồ hệ thống chưa đồng bộ, bỏ MinIO upload");
        return false;
    }

    char date[9], amz_date[17];
    strftime(date, sizeof(date), "%Y%m%d", &utc);
    strftime(amz_date, sizeof(amz_date), "%Y%m%dT%H%M%SZ", &utc);

    char obj[128];
    snprintf(obj, sizeof(obj), "%d/%lu.jpg",
             frame->camera_id, (unsigned long)(s_minio_index + 1));

    char uri[256];
    snprintf(uri, sizeof(uri), "/%s/%s", s_bucket, obj);

    char payload_hash[65];
    if (!sha256_hex(frame->data, frame->len, payload_hash)) return false;

    char can_headers[256];
    snprintf(can_headers, sizeof(can_headers),
             "host:%s\nx-amz-content-sha256:%s\nx-amz-date:%s\n",
             s_endpoint, payload_hash, amz_date);

    char can_req[1200];
    snprintf(can_req, sizeof(can_req),
             "PUT\n%s\n\n%s\nhost;x-amz-content-sha256;x-amz-date\n%s",
             uri, can_headers, payload_hash);

    char can_hash[65];
    if (!sha256_hex((uint8_t *)can_req, strlen(can_req), can_hash)) return false;

    char scope[64];
    snprintf(scope, sizeof(scope), "%s/%s/s3/aws4_request", date, s_region);

    char sts[1200];
    snprintf(sts, sizeof(sts), "AWS4-HMAC-SHA256\n%s\n%s\n%s",
             amz_date, scope, can_hash);

    char kprefix[128];
    snprintf(kprefix, sizeof(kprefix), "AWS4%s", s_secret_key);

    uint8_t kd[32], kr[32], ks[32], kk[32], sig_raw[32];
    if (!hmac_sha256((uint8_t *)kprefix, strlen(kprefix), (uint8_t *)date, strlen(date), kd) ||
        !hmac_sha256(kd, 32, (uint8_t *)s_region, strlen(s_region), kr) ||
        !hmac_sha256(kr, 32, (uint8_t *)"s3", 2, ks) ||
        !hmac_sha256(ks, 32, (uint8_t *)"aws4_request", 12, kk) ||
        !hmac_sha256(kk, 32, (uint8_t *)sts, strlen(sts), sig_raw)) return false;

    char sig_hex[65];
    hex_encode(sig_raw, 32, sig_hex);

    char auth[512];
    snprintf(auth, sizeof(auth),
             "AWS4-HMAC-SHA256 Credential=%s/%s, "
             "SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature=%s",
             s_access_key, scope, sig_hex);

    char url[512];
    snprintf(url, sizeof(url), "%s://%s%s",
             s_use_tls ? "https" : "http", s_endpoint, uri);

    esp_http_client_config_t cfg = {
        .url = url,
        .method = HTTP_METHOD_PUT,
        .crt_bundle_attach = s_use_tls ? esp_crt_bundle_attach : NULL,
        .timeout_ms = 15000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return false;

    esp_http_client_set_header(client, "x-amz-content-sha256", payload_hash);
    esp_http_client_set_header(client, "x-amz-date", amz_date);
    esp_http_client_set_header(client, "Authorization", auth);
    esp_http_client_set_header(client, "Content-Type", "image/jpeg");
    esp_http_client_set_post_field(client, (const char *)frame->data, (int)frame->len);

    esp_err_t err = esp_http_client_perform(client);
    int code = esp_http_client_get_status_code(client);
    bool ok = (err == ESP_OK && code >= 200 && code < 300);

    if (ok) {
        s_minio_index++;
        s_minio_sent++;
    } else {
        ESP_LOGE(TAG, "MinIO thất bại code=%d err=%s", code, esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    return ok;
}

/* ---- LED feedback ---- */

static void on_send_ok(void) {
    if (g_net_error) {
        g_net_error = false;
        led_status_white();
    }
    s_fail_streak = 0;
}

static void on_send_fail(void) {
    s_fail_streak++;
    if (s_fail_streak >= HTTP_MAX_RETRY_COUNT && !g_net_error) {
        g_net_error = true;
        ESP_LOGE(TAG, "Upload liên tục thất bại (%d lần)", s_fail_streak);
    }
    s_led_err_toggle = !s_led_err_toggle;
    led_status_set_rgb(s_led_err_toggle ? 48 : 0, 8, 0);
}

static void build_backend_url(char *out, size_t out_len, const char *path)
{
    if (!out || out_len == 0 || !path) return;

    size_t base_len = strlen(s_server);
    bool base_has_slash = (base_len > 0 && s_server[base_len - 1] == '/');
    bool path_has_slash = (path[0] == '/');

    if (base_has_slash && path_has_slash) {
        snprintf(out, out_len, "%s%s", s_server, path + 1);
    } else if (!base_has_slash && !path_has_slash) {
        snprintf(out, out_len, "%s/%s", s_server, path);
    } else {
        snprintf(out, out_len, "%s%s", s_server, path);
    }
}

static void apply_pending_capture_interval(void)
{
    mqtt_cmd_msg_t cmd;
    if (xQueuePeek(g_mqtt_cmd_queue, &cmd, 0) == pdTRUE &&
        cmd.cmd == MQTT_CMD_CAPTURE_INTERVAL) {
        xQueueReceive(g_mqtt_cmd_queue, &cmd, 0);
        g_capture_interval_ms = (uint32_t)cmd.payload.interval.interval_ms;
        ESP_LOGI(TAG, "Chu kỳ chụp mới -> %lums",
                 (unsigned long)g_capture_interval_ms);
    }
}

/* ---- Main task ---- */

void uploader_task(void *pvParameter)
{
    (void)pvParameter;
    frame_msg_t msg;
    bool prev_state_known = false;
    tl_state_t prev_state = TL_STATE_RED;
    int64_t last_heartbeat_us = 0;

    ESP_LOGI(TAG, "Task tải lên khởi động");

    while (g_system_running) {
        if (g_frames_upload_epoch != s_epoch_seen) {
            s_epoch_seen = g_frames_upload_epoch;
            s_minio_sent = s_minio_index = 0;
            s_limit_logged = false;
            ESP_LOGI(TAG, "Reset bộ đếm MinIO");
        }

        if (xQueueReceive(g_frame_queue, &msg, pdMS_TO_TICKS(100)) != pdTRUE) {
            apply_pending_capture_interval();
            continue;
        }

        tl_state_t current_state = (tl_state_t)msg.traffic_state;

        if (prev_state_known && prev_state == TL_STATE_RED && current_state == TL_STATE_GREEN) {
            if (send_finalize(msg.camera_id)) {
                ESP_LOGI(TAG, "Finalize thành công cam=%d khi chuyển đỏ -> xanh", msg.camera_id);
            }
        }
        prev_state_known = true;
        prev_state = current_state;

        if (current_state != TL_STATE_RED) {
            int64_t now_us = esp_timer_get_time();
            if ((now_us - last_heartbeat_us) >= HEARTBEAT_INTERVAL_US) {
                if (send_heartbeat(msg.camera_id)) {
                    last_heartbeat_us = now_us;
                }
            }
            apply_pending_capture_interval();
            heap_caps_free(msg.data);
            continue;
        }

        bool http_ok = false;
        for (int r = 0; r < HTTP_MAX_RETRY_COUNT && !http_ok; r++) {
            http_ok = send_http(&msg);
            if (!http_ok && r < HTTP_MAX_RETRY_COUNT - 1) {
                vTaskDelay(pdMS_TO_TICKS(HTTP_RETRY_DELAY_MS));
            }
        }

        if (http_ok) {
            g_send_success++;
            on_send_ok();
        } else {
            g_send_fail++;
            on_send_fail();
            task_manager_report_event("upload_fail", "HTTP_err");
        }

        bool minio_active = s_endpoint[0] && s_access_key[0] && s_secret_key[0];
        if (minio_active && g_frames_per_upload > 0) {
            if (s_minio_sent < g_frames_per_upload) {
                s_limit_logged = false;
                bool mok = false;
                for (int r = 0; r < HTTP_MAX_RETRY_COUNT && !mok; r++) {
                    mok = send_minio(&msg);
                    if (!mok && r < HTTP_MAX_RETRY_COUNT - 1) {
                        vTaskDelay(pdMS_TO_TICKS(HTTP_RETRY_DELAY_MS));
                    }
                }
                if (!mok) {
                    ESP_LOGW(TAG, "MinIO thất bại sau %d lần", HTTP_MAX_RETRY_COUNT);
                }
            } else if (!s_limit_logged) {
                s_limit_logged = true;
                ESP_LOGW(TAG, "Đã đạt giới hạn MinIO (%u frames)", (unsigned)g_frames_per_upload);
            }
        }

        apply_pending_capture_interval();
        heap_caps_free(msg.data);
    }

    ESP_LOGI(TAG, "Task tải lên kết thúc");
    vTaskDelete(NULL);
}
