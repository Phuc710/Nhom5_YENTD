/*
 * stream_server.c - HTTP stream server for ESP32.
 */
#include "stream_server.h"

#include <stdio.h>

#include "esp_http_server.h"
#include "esp_log.h"
#include "task_manager.h"

static const char *TAG = "stream_srv";
static httpd_handle_t s_httpd = NULL;

static esp_err_t with_latest_frame(
    esp_err_t (*cb)(httpd_req_t *, const uint8_t *, size_t, void *),
    httpd_req_t *req,
    void *ctx
)
{
    if (!cb || !req || !g_latest_frame_mutex) {
        return ESP_ERR_INVALID_STATE;
    }

    if (xSemaphoreTake(g_latest_frame_mutex, pdMS_TO_TICKS(200)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    if (!g_latest_buf || g_latest_len == 0) {
        xSemaphoreGive(g_latest_frame_mutex);
        return ESP_ERR_NOT_FOUND;
    }

    esp_err_t err = cb(req, g_latest_buf, g_latest_len, ctx);
    xSemaphoreGive(g_latest_frame_mutex);
    return err;
}

static esp_err_t send_snapshot(
    httpd_req_t *req,
    const uint8_t *jpeg,
    size_t jpeg_len,
    void *ctx
)
{
    (void)ctx;
    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_send(req, (const char *)jpeg, (ssize_t)jpeg_len);
}

static esp_err_t send_stream_part(
    httpd_req_t *req,
    const uint8_t *jpeg,
    size_t jpeg_len,
    void *ctx
)
{
    const char *boundary = (const char *)ctx;
    char part_header[96];
    int part_len = snprintf(
        part_header,
        sizeof(part_header),
        "\r\n--%s\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
        boundary,
        (unsigned)jpeg_len
    );

    if (httpd_resp_send_chunk(req, part_header, part_len) != ESP_OK) {
        return ESP_FAIL;
    }
    return httpd_resp_send_chunk(req, (const char *)jpeg, (ssize_t)jpeg_len);
}

static esp_err_t snapshot_handler(httpd_req_t *req)
{
    esp_err_t err = with_latest_frame(send_snapshot, req, NULL);
    if (err != ESP_OK) {
        httpd_resp_set_status(req, "503 Service Unavailable");
        httpd_resp_set_type(req, "application/json");
        return httpd_resp_sendstr(req, "{\"detail\":\"No camera frame available yet\"}");
    }
    return ESP_OK;
}

static esp_err_t stream_handler(httpd_req_t *req)
{
    static const char *boundary = "frame";
    char content_type[64];
    snprintf(content_type, sizeof(content_type), "multipart/x-mixed-replace;boundary=%s", boundary);

    httpd_resp_set_type(req, content_type);
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    g_stream_client_count++;

    while (g_system_running) {
        esp_err_t err = with_latest_frame(send_stream_part, req, (void *)boundary);
        if (err != ESP_OK) {
            if (err == ESP_ERR_TIMEOUT || err == ESP_ERR_NOT_FOUND) {
                vTaskDelay(pdMS_TO_TICKS(50));
                continue;
            }

            ESP_LOGI(TAG, "Stream: client disconnected");
            if (g_stream_client_count > 0) {
                g_stream_client_count--;
            }
            return ESP_FAIL;
        }

        vTaskDelay(pdMS_TO_TICKS(60));
    }

    if (g_stream_client_count > 0) {
        g_stream_client_count--;
    }
    return httpd_resp_send_chunk(req, NULL, 0);
}

static esp_err_t root_handler(httpd_req_t *req)
{
    static const char html[] =
        "<html><head><title>ESP32-S3 Camera</title></head>"
        "<body style='font-family:sans-serif;background:#111;color:#eee;padding:24px'>"
        "<h2>ESP32-S3 Stream</h2>"
        "<p><a href='/snapshot' style='color:#f7d14b'>/snapshot</a></p>"
        "<img src='/stream' style='max-width:100%;border:1px solid #333;border-radius:12px'/>"
        "</body></html>";
    httpd_resp_set_type(req, "text/html");
    return httpd_resp_sendstr(req, html);
}

esp_err_t stream_server_start(void)
{
    if (s_httpd) {
        return ESP_OK;
    }

    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 81;
    config.max_uri_handlers = 8;
    config.stack_size = 8192;

    esp_err_t err = httpd_start(&s_httpd, &config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "HTTP stream start failed (%s)", esp_err_to_name(err));
        return err;
    }

    httpd_uri_t root_uri = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = root_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t snapshot_uri = {
        .uri = "/snapshot",
        .method = HTTP_GET,
        .handler = snapshot_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t stream_uri = {
        .uri = "/stream",
        .method = HTTP_GET,
        .handler = stream_handler,
        .user_ctx = NULL,
    };

    httpd_register_uri_handler(s_httpd, &root_uri);
    httpd_register_uri_handler(s_httpd, &snapshot_uri);
    httpd_register_uri_handler(s_httpd, &stream_uri);

    ESP_LOGI(TAG, "HTTP stream ready on port 81 (/, /snapshot, /stream)");
    return ESP_OK;
}

void stream_server_stop(void)
{
    if (!s_httpd) {
        return;
    }

    httpd_stop(s_httpd);
    s_httpd = NULL;
    ESP_LOGI(TAG, "HTTP stream stopped");
}
