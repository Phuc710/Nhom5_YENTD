#
# Component "main" chuẩn cho PlatformIO + ESP-IDF.
# Toàn bộ mã nguồn firmware thật nằm trực tiếp trong thư mục main/.
#

set(FIRMWARE_SRCS
    "main.c"
    "app_config.c"
    "wifi_manager.c"
    "goouuu_camera.c"
    "stream_server.c"
    "dns_server.c"
    "tb_provisioning.c"
    "backend_sync.c"
    "camera_task.c"
    "mqtt_app.c"
    "task_manager.c"
    "health_task.c"
    "button_task.c"
    "traffic_light.c"
)

set(FIRMWARE_REQUIRES
    nvs_flash
    esp_wifi
    esp_event
    esp_http_client
    esp_https_ota
    esp_http_server
    mqtt
    driver
    esp_timer
    mbedtls
    json
    app_update
    heap
    log
)

idf_component_register(
    SRCS
        ${FIRMWARE_SRCS}
    INCLUDE_DIRS
        "."
        "../include"
    REQUIRES
        ${FIRMWARE_REQUIRES}
)
