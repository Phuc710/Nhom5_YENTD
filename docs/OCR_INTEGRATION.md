# Tài liệu Tích hợp OCR Endpoint (Go Gateway)

Tài liệu này đặc tả chi tiết về việc tích hợp cổng kết nối nhận dạng ký tự quang học (OCR API Gateway) của hệ thống giám sát giao thông thông minh.

- **Base URL**: `http://103.249.117.210:3340`
- **Môi trường**: Thực nghiệm và kiểm thử
- **Công nghệ nền tảng**: Go (High-performance API Gateway)

---

## 1. Danh sách Endpoint OCR

Cổng OCR Gateway hỗ trợ hai phương thức xử lý chính: **Xử lý đồng bộ (Synchronous)** phục vụ kiểm thử nhanh/hiển thị trực tiếp, và **Xử lý bất đồng bộ (Asynchronous via Kafka)** phục vụ đẩy tải luồng lớn từ các thiết bị Camera Edge (ESP32-S3).

### 1.1. Endpoint Xử lý Đồng bộ (`POST /ocr/upload`)

Nhận hình ảnh biển số hoặc khung hình chứa ký tự, thực hiện nhận diện trực tiếp và trả về dữ liệu văn bản kèm tọa độ hộp bao.

*   **HTTP Method**: `POST`
*   **Path**: `/ocr/upload`
*   **Content-Type**: `multipart/form-data`
*   **Request Payload**:
    *   `file` (File, Bắt buộc): File ảnh (định dạng JPEG, PNG hoặc WebP).

*   **Mẫu JSON Response (Thành công - `200 OK`)**:
    ```json
    {
      "success": true,
      "count": 1,
      "results": [
        {
          "box": [4, 38, 6, 2, 358, 8, 356, 44],
          "text": "23062024165357",
          "confidence": 0.995761513710022
        }
      ],
      "message": "Detected 1 text regions"
    }
    ```

*   **Giải thích các trường trả về**:
    *   `success`: Trạng thái xử lý (True/False).
    *   `count`: Số lượng vùng văn bản (biển số) phát hiện được.
    *   `results`: Danh sách kết quả chi tiết.
        *   `box`: Tọa độ 4 góc của hộp bao chữ dưới dạng mảng 8 phần tử xoay vòng `[x1, y1, x2, y2, x3, y3, x4, y4]`.
        *   `text`: Nội dung biển số/ký tự nhận diện được.
        *   `confidence`: Độ tin cậy của thuật toán OCR (từ `0.0` đến `1.0`).
    *   `message`: Thông điệp mô tả trạng thái phản hồi.

---

### 1.2. Endpoint Xử lý Bất đồng bộ (`POST /ocr/kafka`)

Nhận hình ảnh từ các camera giám sát biên (ESP32-S3), lập tức đẩy vào hàng đợi Kafka để xử lý ngầm (Background Workers) nhằm đảm bảo thông lượng tối đa của hệ thống mà không gây nghẽn kết nối mạng của thiết bị IoT.

*   **HTTP Method**: `POST`
*   **Path**: `/ocr/kafka`
*   **Query Parameters**:
    *   `camera_id` (int, Bắt buộc): Định danh ID của camera gửi dữ liệu (ví dụ: `?camera_id=2`).
    *   `save_img` (boolean, Tùy chọn): Lưu trữ ảnh gốc trên máy chủ (mặc định: `false`).
*   **Content-Type**: `multipart/form-data`
*   **Request Payload**:
    *   `file` (File, Bắt buộc): Ảnh chụp từ camera.
    *   `timestamp` (String/Float, Tùy chọn): Thời gian chụp ảnh gửi từ client.

*   **Mẫu JSON Response (Thành công - `200 OK`)**:
    ```json
    {
      "success": true,
      "camera_id": "2",
      "message": "Request received and queued for processing."
    }
    ```

---

## 2. Hướng dẫn Tích hợp (Code Examples)

### 2.1. Tích hợp bằng Python (Đồng bộ)

Sử dụng thư viện `requests` để gửi ảnh lên để nhận diện trực tiếp biển số:

```python
import requests

def perform_ocr(image_path):
    url = "http://103.249.117.210:3340/ocr/upload"
    
    try:
        with open(image_path, 'rb') as f:
            files = {'file': (image_path, f, 'image/jpeg')}
            response = requests.post(url, files=files)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    print(f"Thành công! Phát hiện {data['count']} vùng văn bản:")
                    for result in data['results']:
                        print(f"- Văn bản: {result['text']}")
                        print(f"  Độ tin cậy: {result['confidence'] * 100:.2f}%")
                        print(f"  Tọa độ: {result['box']}")
                else:
                    print(f"Lỗi từ server: {data.get('message')}")
            else:
                print(f"Yêu cầu thất bại với mã lỗi: {response.status_code}")
                
    except Exception as e:
        print(f"Đã xảy ra lỗi kết nối: {e}")

# Chạy thử nghiệm
perform_ocr("test_car.png")
```

---

### 2.2. Tích hợp trên ESP32 C/C++ (Dùng cho Camera Firmware)

Thiết lập gửi ảnh chụp dạng nhị phân JPEG trực tiếp từ buffer camera lên cổng Kafka:

```cpp
#include "esp_http_client.h"

// Cấu hình URL kết nối
const char* ocr_url = "http://103.249.117.210:3340/ocr/kafka?camera_id=2&save_img=false";

esp_err_t upload_image_to_ocr(uint8_t* fb_buf, size_t fb_len) {
    static const char *boundary = "----EspCamBoundary";
    
    // Tạo cấu trúc multipart data
    char prefix[256];
    snprintf(prefix, sizeof(prefix),
             "--%s\r\n"
             "Content-Disposition: form-data; name=\"file\"; filename=\"capture.jpg\"\r\n"
             "Content-Type: image/jpeg\r\n\r\n", boundary);
             
    char suffix[64];
    snprintf(suffix, sizeof(suffix), "\r\n--%s--\r\n", boundary);
    
    size_t body_len = strlen(prefix) + fb_len + strlen(suffix);
    char *body = (char*)malloc(body_len);
    if (!body) return ESP_ERR_NO_MEM;
    
    // Copy dữ liệu vào buffer gửi đi
    size_t offset = 0;
    memcpy(body + offset, prefix, strlen(prefix));
    offset += strlen(prefix);
    memcpy(body + offset, fb_buf, fb_len);
    offset += fb_len;
    memcpy(body + offset, suffix, strlen(suffix));
    
    // Cấu hình Client
    esp_http_client_config_t config = {
        .url = ocr_url,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 10000,
    };
    
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        free(body);
        return ESP_FAIL;
    }
    
    // Thiết lập Headers
    char content_type[128];
    snprintf(content_type, sizeof(content_type), "multipart/form-data; boundary=%s", boundary);
    esp_http_client_set_header(client, "Content-Type", content_type);
    esp_http_client_set_header(client, "Accept", "application/json");
    
    esp_http_client_set_post_field(client, body, body_len);
    
    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    
    if (err == ESP_OK && status == 200) {
        ESP_LOGI("OCR", "Upload thành công, queued vào Kafka.");
    } else {
        ESP_LOGE("OCR", "Upload thất bại. Code: %d, Err: %s", status, esp_err_to_name(err));
    }
    
    esp_http_client_cleanup(client);
    free(body);
    return err;
}
```

---

### 2.3. Tích hợp bằng lệnh `cURL` (Dòng lệnh)

*   **Test gọi đồng bộ lấy kết quả trực tiếp**:
    ```bash
    curl -X POST http://103.249.117.210:3340/ocr/upload \
      -F "file=@/path/to/image.jpg"
    ```

*   **Test gọi đẩy bất đồng bộ (Kafka)**:
    ```bash
    curl -X POST "http://103.249.117.210:3340/ocr/kafka?camera_id=2&save_img=false" \
      -F "file=@/path/to/image.jpg" \
      -F "timestamp=1717165357"
    ```
