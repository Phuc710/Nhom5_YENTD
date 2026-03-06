# Image Processing Pipeline - Production Flow

## 🎯 Vấn Đề

ESP32-CAM chụp outdoor → chỉ ~20% ảnh chất lượng tốt:
- Ảnh mờ (motion blur)
- Cháy/thiếu sáng
- Noise cao  
- OCR sai

**Giải pháp**: Multi-shot (5-7 ảnh) + Quality Scoring + Voting

---

## 📊 Production Pipeline

```
ESP32: Chụp 5 ảnh/detection (interval 1s)
  ↓
Upload ALL lên Backend
  ↓
Backend Processing:
  ├─ 1. Pre-process (denoise, enhance)
  ├─ 2. Quality scoring (sharpness, brightness, contrast)
  ├─ 3. YOLO detect (chỉ ảnh quality >= 70/100)
  ├─ 4. Object tracking (SORT) → track_id
  ├─ 5. OCR per frame
  ├─ 6. Vote results per track_id
  └─ 7. Save nếu vote >= 40%
```

---

## 🧮 Image Quality Metrics

| Metric | Algorithm | Weight |
|--------|-----------|--------|
| Sharpness | Variance of Laplacian | 40% |
| Brightness | Mean pixel (80-180 optimal) | 20% |
| Contrast | Std deviation | 20% |
| Noise | Laplacian mean | 10% |
| Edge density | Canny edges | 10% |

### Code

```python
import cv2
import numpy as np

def calculate_quality_score(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    
    # Sharpness (40%)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    sharpness = min(laplacian_var / 100 * 40, 40)
    
    # Brightness (20%)
    brightness_mean = np.mean(gray)
    brightness = 20 if 80 <= brightness_mean <= 180 else max(0, 20 - abs(brightness_mean - 130) / 10)
    
    # Contrast (20%)
    contrast = min(np.std(gray) / 40 * 20, 20)
    
    # Noise (10%)
    noise_estimate = np.mean(np.abs(cv2.Laplacian(gray, cv2.CV_64F)))
    noise = max(0, 10 - noise_estimate / 50 * 10)
    
    # Edge density (10%)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.sum(edges > 0) / edges.size
    edge_score = min(edge_density * 100 / 30 * 10, 10)
    
    return round(sharpness + brightness + contrast + noise + edge_score, 2)
```

---

## 🗳️ Voting Mechanism

```python
from collections import Counter

def vote_ocr_results(ocr_results):
    """
    Args: [{plate, confidence, image_id}, ...]
    Returns: {plate, vote_count, vote_percent, avg_confidence}
    """
    valid = [r for r in ocr_results if r.get("license_plate")]
    if not valid:
        return None
    
    plates = [r["license_plate"] for r in valid]
    winner, count = Counter(plates).most_common(1)[0]
    
    matching = [r for r in valid if r["license_plate"] == winner]
    avg_conf = sum(r["confidence"] for r in matching) / len(matching)
    
    return {
        "license_plate": winner,
        "vote_count": count,
        "vote_percent": round(count / len(ocr_results) * 100, 2),
        "avg_confidence": round(avg_conf, 4)
    }
```

**Example**:
```
5 frames OCR:
  51F12345 (3 votes) ✅ WINNER
  51F1234S (1 vote)
  None (1 vote)
  
→ Result: 51F12345 (60% confidence)
```

---

## 🌧️ Harsh Weather Handling

### Pre-processing

```python
def preprocess_image(image):
    # Denoise
    denoised = cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
    
    # CLAHE (tăng contrast)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8)).apply(l)
    enhanced = cv2.cvtColor(cv2.merge([l,a,b]), cv2.COLOR_LAB2BGR)
    
    # Sharpen
    kernel = np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]])
    return cv2.filter2D(enhanced, -1, kernel)
```

### Adaptive Config

```python
# Normal conditions
CAPTURE_COUNT = 5
MIN_VOTE_THRESHOLD = 2  # 40%

# Bad weather / night (detect via timestamp or sensor)
CAPTURE_COUNT = 7
MIN_VOTE_THRESHOLD = 4  # 57%
```

### Night Mode (ESP32)

```cpp
sensor_t* s = esp_camera_sensor_get();
s->set_exposure_ctrl(s, 1);
s->set_aec_value(s, 1200);
s->set_gain_ctrl(s, 1);
s->set_agc_gain(s, 30);
s->set_brightness(s, 2);
s->set_contrast(s, 2);
```

---

## 📦 Complete Backend Flow

```python
async def process_violation(files: List[UploadFile], camera_id: int):
    images = []
    for file in files:
        img = cv2.imdecode(np.frombuffer(await file.read(), np.uint8), cv2.IMREAD_COLOR)
        img = preprocess_image(img)
        score = calculate_quality_score(img)
        images.append({"img": img, "score": score})
    
    # Filter quality >= 70
    good_images = [x for x in images if x["score"] >= 70]
    if not good_images:
        return {"error": "No quality images"}
    
    # YOLO + OCR + Tracking
    tracker = Sort()
    track_ocr_history = {}
    
    for i, img_data in enumerate(good_images):
        vehicles = yolo_detect_vehicles(img_data["img"])
        tracked = tracker.update(vehicles)
        
        for track in tracked:
            track_id = int(track[4])
            plate = yolo_detect_plate(img_data["img"], track[:4])
            if plate:
                ocr = perform_ocr(plate)
                track_ocr_history.setdefault(track_id, []).append(ocr)
    
    # Vote per track
    violations = []
    for track_id, ocr_results in track_ocr_history.items():
        result = vote_ocr_results(ocr_results)
        if result and result["vote_count"] >= MIN_VOTE_THRESHOLD:
            violations.append(await save_violation(camera_id, result))
    
    return violations
```

---

## ✅ Production Config

```python
# Config
CAPTURE_INTERVAL = 1000  # ms
CAPTURE_COUNT = 5
QUALITY_THRESHOLD = 70
VOTE_THRESHOLD = 2  # 40%

# Harsh weather
if is_harsh_weather():
    CAPTURE_COUNT = 7
    VOTE_THRESHOLD = 4  # 57%
```

**Metrics Tracking**:
- Average quality score per camera
- Voting success rate
- OCR accuracy
- Processing time
