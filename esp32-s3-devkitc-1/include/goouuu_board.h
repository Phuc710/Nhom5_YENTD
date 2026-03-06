#pragma once

/* ============================================================
 * GOOUUU Tech ESP32-S3 N16R8 — Pin Map
 *
 * SoC:    ESP32-S3 (Xtensa LX7 dual-core 240MHz)
 * Flash:  16MB (N16)
 * PSRAM:  8MB OPI (R8)
 * Camera: OV5640 (DVP interface)
 * LED:    WS2812B tích hợp (GPIO 48)
 * Button: BOOT (GPIO 0)
 * ============================================================ */

#define GOOUUU_BOARD_NAME "GOOUUU Tech ESP32-S3-CAM N16R8"

/* ---- UART ------------------------------------------------- */
#define GOOUUU_GPIO_TXD  43
#define GOOUUU_GPIO_RXD  44
#define GOOUUU_GPIO_RGB  48   // WS2812B LED tích hợp

/* ---- Buttons ---------------------------------------------- */
#define GOOUUU_GPIO_BOOT 0
#define GOOUUU_GPIO_RST  21

/* ---- I2C (OLED header) ------------------------------------ */
#define GOOUUU_I2C_SCL   41
#define GOOUUU_I2C_SDA   42

/* ---- TFT ILI9341 (SPI) ------------------------------------ */
#define GOOUUU_TFT_SCK   3
#define GOOUUU_TFT_MISO  46
#define GOOUUU_TFT_MOSI  45
#define GOOUUU_TFT_CS    14
#define GOOUUU_TFT_DC    47
#define GOOUUU_TFT_RST   21

/* ---- Touch XPT2046 ---------------------------------------- */
#define GOOUUU_TOUCH_CS  1
#define GOOUUU_TOUCH_DIN 2
#define GOOUUU_TOUCH_CLK 42
#define GOOUUU_TOUCH_DO  41

/* ---- SD Card (SDIO) --------------------------------------- */
#define GOOUUU_SD_CMD    38
#define GOOUUU_SD_CLK    39
#define GOOUUU_SD_DATA   40

/* ---- Camera DVP (OV5640) ---------------------------------- */
/* Không có PWDN/RESET pin — boot ổn định không cần */
#define GOOUUU_CAM_PWDN   -1
#define GOOUUU_CAM_RESET  -1
#define GOOUUU_CAM_XCLK   15
#define GOOUUU_CAM_SIOD    4   // SCCB SDA (I2C camera)
#define GOOUUU_CAM_SIOC    5   // SCCB SCL (I2C camera)
#define GOOUUU_CAM_VSYNC   6
#define GOOUUU_CAM_HREF    7
#define GOOUUU_CAM_Y9     16   // D7
#define GOOUUU_CAM_Y8     17   // D6
#define GOOUUU_CAM_Y7     18   // D5
#define GOOUUU_CAM_Y6     12   // D4
#define GOOUUU_CAM_Y5     10   // D3
#define GOOUUU_CAM_Y4      8   // D2
#define GOOUUU_CAM_Y3      9   // D1
#define GOOUUU_CAM_Y2     11   // D0
#define GOOUUU_CAM_PCLK   13
#define GOOUUU_CAM_XCLK_FREQ_HZ 20000000

/* ---- Aliases chuẩn CAM_PIN_* (esp32-camera) -------------- */
#define CAM_PIN_PWDN   GOOUUU_CAM_PWDN
#define CAM_PIN_RESET  GOOUUU_CAM_RESET
#define CAM_PIN_XCLK   GOOUUU_CAM_XCLK
#define CAM_PIN_SIOD   GOOUUU_CAM_SIOD
#define CAM_PIN_SIOC   GOOUUU_CAM_SIOC
#define CAM_PIN_D7     GOOUUU_CAM_Y9
#define CAM_PIN_D6     GOOUUU_CAM_Y8
#define CAM_PIN_D5     GOOUUU_CAM_Y7
#define CAM_PIN_D4     GOOUUU_CAM_Y6
#define CAM_PIN_D3     GOOUUU_CAM_Y5
#define CAM_PIN_D2     GOOUUU_CAM_Y4
#define CAM_PIN_D1     GOOUUU_CAM_Y3
#define CAM_PIN_D0     GOOUUU_CAM_Y2
#define CAM_PIN_VSYNC  GOOUUU_CAM_VSYNC
#define CAM_PIN_HREF   GOOUUU_CAM_HREF
#define CAM_PIN_PCLK   GOOUUU_CAM_PCLK

/* ---- Aliases D0..D7 --------------------------------------- */
#define GOOUUU_CAM_D0  GOOUUU_CAM_Y2
#define GOOUUU_CAM_D1  GOOUUU_CAM_Y3
#define GOOUUU_CAM_D2  GOOUUU_CAM_Y4
#define GOOUUU_CAM_D3  GOOUUU_CAM_Y5
#define GOOUUU_CAM_D4  GOOUUU_CAM_Y6
#define GOOUUU_CAM_D5  GOOUUU_CAM_Y7
#define GOOUUU_CAM_D6  GOOUUU_CAM_Y8
#define GOOUUU_CAM_D7  GOOUUU_CAM_Y9
