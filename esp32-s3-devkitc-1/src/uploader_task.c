/*
 * uploader_task.c — Upload frame lên backend HTTP và MinIO/S3
 *
 * Telemetry export (đọc bởi health_task):
 *   g_last_upload_ok    — lần upload cuối thành công không
 *   g_last_http_code    — HTTP status code cuối
 *   g_last_latency_ms   — Độ trễ upload cuối (ms)
 */
#include "task_manager.h"
#include "uploader_task.h"
#include "led_status.h"
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

/*
 * Telemetry export — DEFINITIONS here (uploader là owner đúng).
 * health_task.c và các nơi khác chỉ cần `extern`.
 */
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

/* Backend server — đặt trong platformio.ini:
 *   -DBACKEND_UPLOAD_URL=\"http://your-host:3340\"             */
#ifndef BACKEND_UPLOAD_URL
#  error "BACKEND_UPLOAD_URL chưa được định nghĩa! Thêm vào platformio.ini build_flags."
#endif

/* Backend server */
static char s_server[128] = BACKEND_UPLOAD_URL;
static char s_token[128]  = {0};
static bool s_has_token   = false;

/* Thống kê connection */
static int  s_fail_streak     = 0;
static bool s_led_err_toggle  = false;

/* ---- Public setters ---- */

void uploader_set_token(const char *tok) {
    if (tok && tok[0]) {
        strncpy(s_token, tok, sizeof(s_token)-1);
        s_has_token = true;
    }
}

void uploader_set_server(const char *host, int cam_id) {
    if (host && host[0]) strncpy(s_server, host, sizeof(s_server)-1);
    g_camera_id = cam_id;
}

void uploader_set_minio_config(const char *ep, const char *ak,
                               const char *sk, const char *bucket,
                               const char *region, int use_tls) {
    if (ep)     { ep[0]     ? strncpy(s_endpoint,  ep,     sizeof(s_endpoint)-1)   : (void)(s_endpoint[0]=0); }
    if (ak)     { ak[0]     ? strncpy(s_access_key,ak,     sizeof(s_access_key)-1) : (void)(s_access_key[0]=0); }
    if (sk)     { sk[0]     ? strncpy(s_secret_key,sk,     sizeof(s_secret_key)-1) : (void)(s_secret_key[0]=0); }
    if (bucket) { bucket[0] ? strncpy(s_bucket,    bucket, sizeof(s_bucket)-1)     : (void)(s_bucket[0]=0); }
    if (region) { region[0] ? strncpy(s_region,    region, sizeof(s_region)-1)     : (void)(s_region[0]=0); }
    if (use_tls >= 0) s_use_tls = (use_tls != 0);
    if (!s_bucket[0]) strncpy(s_bucket, "cam",       sizeof(s_bucket)-1);
    if (!s_region[0]) strncpy(s_region, "us-east-1", sizeof(s_region)-1);
    s_minio_sent = s_minio_index = 0;
    s_limit_logged = false;
    ESP_LOGI(TAG, "MinIO: %s/%s (TLS=%s)", s_endpoint, s_bucket,
             s_use_tls ? "bật" : "tắt");
}

/* ---- Crypto helpers ---- */

static void hex_encode(const uint8_t *in, size_t len, char *out) {
    static const char h[] = "0123456789abcdef";
    for (size_t i = 0; i < len; i++) {
        out[i*2] = h[in[i]>>4]; out[i*2+1] = h[in[i]&0xF];
    }
    out[len*2] = '\0';
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

    char url[280];
    snprintf(url, sizeof(url), "%s/ocr/kafka?camera_id=%d&save_img=%s",
             s_server, frame->camera_id, g_save_img ? "true" : "false");

    const char *pre_fmt =
        "--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"img.jpg\"\r\n"
        "Content-Type: image/jpeg\r\n\r\n";
    const char *suf_fmt = "\r\n--%s--\r\n";

    int pre_len = snprintf(NULL, 0, pre_fmt, BOUNDARY);
    int suf_len = snprintf(NULL, 0, suf_fmt, BOUNDARY);
    if (pre_len < 0 || suf_len < 0) return false;

    size_t total = pre_len + frame->len + suf_len;
    char *body = malloc(total + 1);
    if (!body) { ESP_LOGE(TAG, "Không đủ RAM cho body"); return false; }

    sprintf(body, pre_fmt, BOUNDARY);
    memcpy(body + pre_len, frame->data, frame->len);
    sprintf(body + pre_len + frame->len, suf_fmt, BOUNDARY);

    esp_http_client_config_t cfg = {
        .url    = url,
        .method = HTTP_METHOD_POST,
    };
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
    esp_http_client_set_post_field(client, body, total);

    int64_t t0 = esp_timer_get_time();
    esp_err_t err = esp_http_client_perform(client);
    int64_t t1 = esp_timer_get_time();

    int code  = esp_http_client_get_status_code(client);
    bool ok   = (err == ESP_OK && code >= 200 && code < 300);
    uint32_t lat = (uint32_t)((t1 - t0) / 1000LL);

    /* Cập nhật telemetry cho health_task */
    g_last_upload_ok  = ok;
    g_last_http_code  = code;
    g_last_latency_ms = lat;

    if (ok)
        ESP_LOGI(TAG, "Upload OK seq=%lu %u bytes HTTP=%d %lums",
                 (unsigned long)frame->sequence, (unsigned)frame->len, code, (unsigned long)lat);
    else
        ESP_LOGE(TAG, "Upload thất bại HTTP=%d err=%s", code, esp_err_to_name(err));

    esp_http_client_cleanup(client);
    free(body);
    return ok;
}

/* ---- MinIO S3 signed upload ---- */

static bool send_minio(const frame_msg_t *frame)
{
    if (!s_endpoint[0] || !s_access_key[0] || !s_secret_key[0]) return false;

    time_t now = 0; time(&now);
    struct tm utc = {0}; gmtime_r(&now, &utc);
    if (utc.tm_year + 1900 < 2020) {
        ESP_LOGE(TAG, "Đồng hồ hệ thống chưa đồng bộ, bỏ MinIO upload");
        return false;
    }

    char date[9], amz_date[17];
    strftime(date,     sizeof(date),     "%Y%m%d",          &utc);
    strftime(amz_date, sizeof(amz_date), "%Y%m%dT%H%M%SZ",  &utc);

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

    uint8_t kd[32],kr[32],ks[32],kk[32],sig_raw[32];
    if (!hmac_sha256((uint8_t*)kprefix, strlen(kprefix),
                     (uint8_t*)date, strlen(date), kd) ||
        !hmac_sha256(kd,32,(uint8_t*)s_region,strlen(s_region),kr) ||
        !hmac_sha256(kr,32,(uint8_t*)"s3",2,ks) ||
        !hmac_sha256(ks,32,(uint8_t*)"aws4_request",12,kk) ||
        !hmac_sha256(kk,32,(uint8_t*)sts,strlen(sts),sig_raw)) return false;

    char sig_hex[65]; hex_encode(sig_raw, 32, sig_hex);

    char auth[512];
    snprintf(auth, sizeof(auth),
             "AWS4-HMAC-SHA256 Credential=%s/%s, "
             "SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature=%s",
             s_access_key, scope, sig_hex);

    char url[320];
    snprintf(url, sizeof(url), "%s://%s%s",
             s_use_tls ? "https" : "http", s_endpoint, uri);

    esp_http_client_config_t cfg = {
        .url    = url,
        .method = HTTP_METHOD_PUT,
        .crt_bundle_attach = s_use_tls ? esp_crt_bundle_attach : NULL,
        .timeout_ms = 15000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) return false;

    esp_http_client_set_header(client, "x-amz-content-sha256", payload_hash);
    esp_http_client_set_header(client, "x-amz-date",           amz_date);
    esp_http_client_set_header(client, "Authorization",         auth);
    esp_http_client_set_header(client, "Content-Type",          "image/jpeg");
    esp_http_client_set_post_field(client, (const char*)frame->data, frame->len);

    esp_err_t err = esp_http_client_perform(client);
    int code = esp_http_client_get_status_code(client);
    bool ok  = (err == ESP_OK && code >= 200 && code < 300);

    if (ok) { s_minio_index++; s_minio_sent++; }
    else
        ESP_LOGE(TAG, "MinIO thất bại code=%d err=%s", code, esp_err_to_name(err));

    esp_http_client_cleanup(client);
    return ok;
}

/* ---- LED feedback ---- */

static void on_send_ok(void) {
    if (g_net_error) { g_net_error = false; led_status_white(); }
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

/* ---- Task chính ---- */

void uploader_task(void *pvParameter)
{
    (void)pvParameter;
    frame_msg_t msg;

    ESP_LOGI(TAG, "Uploader task khởi động");

    while (g_system_running) {
        /* Reset bộ đếm MinIO khi epoch thay đổi */
        if (g_frames_upload_epoch != s_epoch_seen) {
            s_epoch_seen = g_frames_upload_epoch;
            s_minio_sent = s_minio_index = 0;
            s_limit_logged = false;
            ESP_LOGI(TAG, "Reset bộ đếm MinIO");
        }

        if (xQueueReceive(g_frame_queue, &msg, pdMS_TO_TICKS(100)) != pdTRUE)
            continue;

        /* --- Upload lên backend --- */
        bool http_ok = false;
        for (int r = 0; r < HTTP_MAX_RETRY_COUNT && !http_ok; r++) {
            http_ok = send_http(&msg);
            if (!http_ok && r < HTTP_MAX_RETRY_COUNT - 1)
                vTaskDelay(pdMS_TO_TICKS(HTTP_RETRY_DELAY_MS));
        }

        if (http_ok) { g_send_success++; on_send_ok(); }
        else         { g_send_fail++; on_send_fail();
                       task_manager_report_event("upload_fail", "HTTP_err"); }

        /* --- Upload lên MinIO (nếu đã config và chưa đạt limit) --- */
        bool minio_active = s_endpoint[0] && s_access_key[0] && s_secret_key[0];
        if (minio_active && g_frames_per_upload > 0) {
            if (s_minio_sent < g_frames_per_upload) {
                s_limit_logged = false;
                bool mok = false;
                for (int r = 0; r < HTTP_MAX_RETRY_COUNT && !mok; r++) {
                    mok = send_minio(&msg);
                    if (!mok && r < HTTP_MAX_RETRY_COUNT - 1)
                        vTaskDelay(pdMS_TO_TICKS(HTTP_RETRY_DELAY_MS));
                }
                if (!mok) ESP_LOGW(TAG, "MinIO thất bại sau %d lần", HTTP_MAX_RETRY_COUNT);
            } else if (!s_limit_logged) {
                s_limit_logged = true;
                ESP_LOGW(TAG, "Đã đạt giới hạn MinIO (%u frames)", (unsigned)g_frames_per_upload);
            }
        }

        /* Kiểm tra lệnh đổi interval từ MQTT */
        mqtt_cmd_msg_t cmd;
        if (xQueuePeek(g_mqtt_cmd_queue, &cmd, 0) == pdTRUE &&
            cmd.cmd == MQTT_CMD_CAPTURE_INTERVAL) {
            xQueueReceive(g_mqtt_cmd_queue, &cmd, 0);
            g_capture_interval_ms = (uint32_t)cmd.payload.interval.interval_ms;
            ESP_LOGI(TAG, "Capture interval → %lums",
                     (unsigned long)g_capture_interval_ms);
        }

        /* Giải phóng PSRAM frame buffer */
        heap_caps_free(msg.data);
    }

    ESP_LOGI(TAG, "Uploader task kết thúc");
    vTaskDelete(NULL);
}
