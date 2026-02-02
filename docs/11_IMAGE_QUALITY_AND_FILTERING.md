# Image Quality Scoring & Multi-Shot Filtering

## 🎯 Vấn Đề: ESP32-CAM Chụp Nhiều Ảnh Chất Lượng Khác Nhau

### Thực Tế Khi Chụp Liên Tiếp

ESP32-CAM chụp ảnh trong điều kiện thực tế (outdoor, đèn đỏ 9s):

| Vấn Đề | Nguyên Nhân | Tỉ Lệ |
|--------|-------------|-------|
| Ảnh mờ | Motion blur, camera không kịp focus | ~20% |
| Cháy sáng | Ánh nắng mạnh, phản chiếu | ~15% |
| Thiếu sáng | Ban đêm, mưa, mây | ~15% |
| Noise cao | ISO cao, sensor nhỏ | ~10% |
| OCR sai | Biển số bị che, góc xiên | ~20% |
| **Ảnh tốt** | **Chất lượng OK** | **~20%** |

**Kết luận**: Không thể tin 1 ảnh đơn lẻ!

### Timing: Đèn Đỏ 9 Giây

```
Đèn Đỏ: 9s
Đèn Xanh: 7s  
Đèn Vàng: 2s
Capture Interval: 1s/ảnh

→ Trong 1 chu kỳ đèn đỏ: MAX 9 ảnh
```

**Ví dụ thực tế**:
```
Xe A đi qua khi đèn đỏ:
  t=0s  → Chụp ảnh 1: Xe vừa vào khung hình (góc xa, mờ)
  t=1s  → Chụp ảnh 2: Xe ở giữa (RÕ NÉT) ✅
  t=2s  → Chụp ảnh 3: Xe đã qua (motion blur)
  t=3s  → Chụp ảnh 4: Xe ra khỏi frame
  
Xe B đi qua:
  t=4s  → Chụp ảnh 5: Xe B vào (rõ nét) ✅
  t=5s  → Chụp ảnh 6: Xe B giữa (cháy sáng)
  t=6s  → Chụp ảnh 7: Xe B ra
  
→ Có 7 ảnh, nhưng chỉ có 2-3 ảnh CHẤT LƯỢNG TỐT
```

## 📊 Chiến Lược: Multi-Shot + Image Quality Scoring

### Cách 1 – Chọn 1 Ảnh Tốt Nhất (Image Quality Scoring) ⭐⭐⭐

**Quy trình**:
```
ESP32-CAM chụp liên tiếp
 └─ Mỗi ảnh → Đánh giá chất lượng (scoring)
      └─ Chọn ảnh có score CAO NHẤT
           └─ Upload lên backend
```

#### 📌 Tiêu Chí Chấm Điểm Ảnh (IMAGE QUALITY METRICS)

| Tiêu chí | Cách đo | Ngưỡng tốt | Trọng số |
|----------|---------|------------|----------|
| **Độ nét** (Sharpness) | Variance of Laplacian | > 100 | 40% |
| **Độ sáng** (Brightness) | Mean pixel value | 80-180 | 20% |
| **Tương phản** (Contrast) | Std deviation | > 40 | 20% |
| **Noise** (Nhiễu) | Laplacian / FFT | < 50 | 10% |
| **Motion blur** | Edge density | > 30 | 10% |

#### Code: Image Quality Scoring (Backend hoặc ESP32)

```python
import cv2
import numpy as np

def calculate_image_quality_score(image):
    """
    Tính điểm chất lượng ảnh (0-100)
    
    Args:
        image: numpy array (BGR hoặc grayscale)
    
    Returns:
        score: float (0-100)
    """
    # Convert sang grayscale nếu cần
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    # === 1. SHARPNESS (Độ Nét) - 40% ===
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    sharpness_score = min(laplacian_var / 100 * 40, 40)  # Max 40 points
    
    # === 2. BRIGHTNESS (Độ Sáng) - 20% ===
    mean_brightness = np.mean(gray)
    # Optimal range: 80-180
    if 80 <= mean_brightness <= 180:
        brightness_score = 20
    elif mean_brightness < 80:  # Too dark
        brightness_score = (mean_brightness / 80) * 20
    else:  # Too bright (> 180)
        brightness_score = max(0, 20 - (mean_brightness - 180) / 10)
    
    # === 3. CONTRAST (Tương Phản) - 20% ===
    std_dev = np.std(gray)
    contrast_score = min(std_dev / 40 * 20, 20)  # Max 20 points
    
    # === 4. NOISE (Nhiễu) - 10% ===
    # Sử dụng Laplacian để ước lượng noise
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    noise_estimate = np.mean(np.abs(laplacian))
    noise_score = max(0, 10 - (noise_estimate / 50 * 10))  # Penalty nếu noise cao
    
    # === 5. MOTION BLUR (Độ Mờ Do Chuyển Động) - 10% ===
    # Edge density: Nhiều cạnh rõ nét = không bị blur
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.sum(edges > 0) / edges.size
    motion_blur_score = min(edge_density * 100 / 30 * 10, 10)  # Max 10 points
    
    # === TỔNG ĐIỂM ===
    total_score = sharpness_score + brightness_score + contrast_score + noise_score + motion_blur_score
    
    return round(total_score, 2)


def get_image_quality_details(image):
    """Chi tiết từng metric để debug"""
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    mean_brightness = np.mean(gray)
    std_dev = np.std(gray)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    noise_estimate = np.mean(np.abs(laplacian))
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.sum(edges > 0) / edges.size * 100
    
    return {
        "sharpness_variance": round(laplacian_var, 2),
        "brightness_mean": round(mean_brightness, 2),
        "contrast_std": round(std_dev, 2),
        "noise_estimate": round(noise_estimate, 2),
        "edge_density_percent": round(edge_density, 2)
    }
```

#### Sử Dụng trong Pipeline

**Option A: ESP32 chấm điểm (cần PSRAM)**
```cpp
// Cần thư viện OpenCV-ESP32 (nặng, không khuyến nghị)
// Hoặc implement simplified version

float calculate_sharpness(uint8_t* img, int width, int height) {
    // Simplified Laplacian variance
    // Code ở đây...
}
```

**Option B: Backend chấm điểm (KHUYẾN NGHỊ)** ⭐
```
ESP32 → Upload 5 ảnh liên tiếp lên backend
Backend → Chấm điểm từng ảnh
       → Chọn ảnh tốt nhất
       → Chạy YOLO + OCR chỉ trên ảnh đó
       → Lưu vào database
```

```python
# Backend - api/upload.py
async def process_uploaded_images(files: List[UploadFile], camera_id: int):
    """Xử lý nhiều ảnh, chọn ảnh tốt nhất"""
    
    image_scores = []
    
    for file in files:
        # Đọc ảnh
        img_data = await file.read()
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Tính điểm
        score = calculate_image_quality_score(img)
        
        image_scores.append({
            "filename": file.filename,
            "image": img,
            "score": score
        })
    
    # Sắp xếp theo score giảm dần
    image_scores.sort(key=lambda x: x["score"], reverse=True)
    
    # Lấy ảnh tốt nhất
    best_image = image_scores[0]
    
    print(f"✅ Best image: {best_image['filename']} (score: {best_image['score']})")
    
    # Chỉ xử lý ảnh tốt nhất
    result = await detect_and_ocr(best_image["image"], camera_id)
    
    return result
```

### Cách 2 – Voting Kết Quả (CÁCH TỐT NHẤT CHO BSX) ⭐⭐⭐⭐⭐

**⚠️ Đừng vote ảnh – vote KẾT QUẢ**

**Quy trình**:
```
ESP32 chụp 5 ảnh
 └─ Upload tất cả lên backend
      └─ YOLO detect + OCR trên TẤT CẢ 5 ảnh
           └─ Thu được 5 kết quả OCR (có thể trùng)
                └─ Vote: Kết quả nào xuất hiện NHIỀU NHẤT
                     └─ Đó là biển số chính xác!
```

**Ví dụ**:

ESP32 chụp 5 ảnh → OCR biển số:

| Ảnh | Kết quả OCR | Quality Score |
|-----|-------------|---------------|
| 1   | 51F12345    | 85            |
| 2   | 51F12345    | 92            |
| 3   | 51F1234S ❌ | 78            |
| 4   | 51F12345    | 88            |
| 5   | None ❌      | 45            |

**Vote**:
- `51F12345`: **3 phiếu** ← WINNER ✅
- `51F1234S`: 1 phiếu
- `None`: 1 phiếu

**Kết luận**: Biển số là **`51F12345`** (confidence: 3/5 = 60%)

#### Code: Voting Mechanism

```python
from collections import Counter

def vote_license_plates(ocr_results: List[dict]) -> dict:
    """
    Vote kết quả OCR từ nhiều ảnh
    
    Args:
        ocr_results: List of {"license_plate": str, "confidence": float, "image_id": int}
    
    Returns:
        {"license_plate": str, "vote_count": int, "confidence": float}
    """
    # Lọc bỏ kết quả None hoặc rỗng
    valid_results = [r for r in ocr_results if r.get("license_plate")]
    
    if not valid_results:
        return {"license_plate": None, "vote_count": 0, "confidence": 0.0}
    
    # Đếm số lần xuất hiện của mỗi biển số
    plates = [r["license_plate"] for r in valid_results]
    vote_counts = Counter(plates)
    
    # Lấy biển số có số phiếu cao nhất
    most_common_plate, vote_count = vote_counts.most_common(1)[0]
    
    # Tính confidence trung bình của biển số này
    matching_results = [r for r in valid_results if r["license_plate"] == most_common_plate]
    avg_confidence = sum(r["confidence"] for r in matching_results) / len(matching_results)
    
    return {
        "license_plate": most_common_plate,
        "vote_count": vote_count,
        "total_images": len(ocr_results),
        "vote_percent": round(vote_count / len(ocr_results) * 100, 2),
        "avg_confidence": round(avg_confidence, 4)
    }


# Sử dụng trong pipeline
async def process_multi_shot(files: List[UploadFile], camera_id: int):
    """Xử lý nhiều ảnh với voting"""
    
    ocr_results = []
    
    for i, file in enumerate(files):
        img_data = await file.read()
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # YOLO detect + OCR
        plates = detect_license_plates(img)
        
        for plate in plates:
            ocr_result = perform_ocr(plate["crop"])
            ocr_results.append({
                "license_plate": ocr_result["text"],
                "confidence": ocr_result["confidence"],
                "image_id": i
            })
    
    # Vote kết quả
    final_result = vote_license_plates(ocr_results)
    
    print(f"✅ Final result: {final_result}")
    
    # Chỉ lưu vào DB nếu vote_count >= ngưỡng (ví dụ: >= 2)
    if final_result["vote_count"] >= 2:
        return await create_violation(camera_id, final_result)
    else:
        print("⚠️ Low confidence, skip")
        return None
```

## 🌧️ Xử Lý Điều Kiện Thời Tiết Khắc Nghiệt

### Mưa, Gió, Bụi

**Vấn đề**:
- Nước mưa trên lens → ảnh mờ
- Bụi/lá cây → occlusion
- Gió mạnh → camera rung

**Giải pháp**:

1. **Pre-processing nâng cao**:
```python
def preprocess_for_harsh_weather(image):
    """Preprocessing cho điều kiện thời tiết xấu"""
    
    # 1. Denoising
    denoised = cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
    
    # 2. Tăng độ tương phản (CLAHE)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    enhanced = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    
    # 3. Sharpen
    kernel = np.array([[-1, -1, -1],
                       [-1,  9, -1],
                       [-1, -1, -1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    
    return sharpened
```

2. **Tăng số lượng ảnh chụp**:
```
Điều kiện tốt: 3-5 ảnh
Điều kiện xấu (mưa, đêm): 7-9 ảnh
```

3. **Ngưỡng vote cao hơn**:
```python
# Điều kiện tốt
MIN_VOTE_COUNT = 2  # 2/5 = 40%

# Điều kiện xấu (detect qua timestamp/sensor)
MIN_VOTE_COUNT = 4  # 4/7 = 57%
```

### Ban Đêm / Thiếu Sáng

1. **Camera settings**:
```cpp
// ESP32-CAM config cho ban đêm
sensor_t* s = esp_camera_sensor_get();
s->set_exposure_ctrl(s, 1);       // Auto exposure
s->set_aec_value(s, 1200);        // Tăng exposure time
s->set_gain_ctrl(s, 1);           // Auto gain
s->set_agc_gain(s, 30);           // Tăng gain (ISO)
s->set_brightness(s, 2);          // Tăng brightness
s->set_contrast(s, 2);            // Tăng contrast
```

2. **Image enhancement**:
```python
def enhance_low_light(image):
    """Tăng cường ảnh thiếu sáng"""
    # Gamma correction
    gamma = 1.5
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255
                      for i in np.arange(0, 256)]).astype("uint8")
    enhanced = cv2.LUT(image, table)
    return enhanced
```

## 📈 Metrics & Monitoring

### Log Image Quality

```python
# Backend - Save quality metrics
violation_data = {
    "camera_id": camera_id,
    "license_plate": "51F12345",
    "quality_metrics": {
        "sharpness": 85.5,
        "brightness": 142.3,
        "contrast": 58.2,
        "noise": 12.4,
        "edge_density": 45.6,
        "overall_score": 88.2
    },
    "vote_metrics": {
        "total_images": 5,
        "successful_ocr": 4,
        "vote_count": 3,
        "vote_percent": 60.0
    }
}
```

### Dashboard Monitoring

Track:
- Average image quality score theo camera
- Voting success rate
- OCR accuracy (nếu có ground truth)
- Rejection rate (ảnh bị loại vì quality thấp)

## ✅ Summary: Chiến Lược Tốt Nhất

```
ESP32-CAM (Outdoor, Real-World)
 └─ Chụp 5-7 ảnh liên tiếp trong đèn đỏ
      └─ Upload TẤT CẢ lên backend
           └─ Backend:
                ├─ Preprocess (denoise, enhance)
                ├─ Quality scoring cho mỗi ảnh
                ├─ YOLO + OCR trên ảnh quality >= 70
                ├─ Vote kết quả OCR
                └─ Lưu nếu vote_count >= 50%
```

**Recommended Config**:
- Normal: 5 ảnh, vote_threshold=2 (40%)
- Harsh weather: 7 ảnh, vote_threshold=4 (57%)
- Night: 7 ảnh + image enhancement
