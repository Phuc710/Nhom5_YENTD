# License Plate Detection & Voting Mechanism

## 🎯 Thách Thức: Nhiều Xe, Nhiều Biển Số Trong 1 Frame

### Scenario Thực Tế

```
Đèn đỏ 9 giây → Có thể có 3-5 xe vượt đèn trong cùng lúc:

Frame 1 (t=0s):  Xe A vào
Frame 2 (t=1s):  Xe A (giữa), Xe B vào
Frame 3 (t=2s):  Xe A ra, Xe B (giữa), Xe C vào
Frame 4 (t=3s):  Xe B ra, Xe C (giữa), Xe D vào
...

THÁCH THỨC:
  ├─ 1 frame có thể chứa 2-3 xe
  ├─ Mỗi xe xuất hiện trong 2-4 frame
  ├─ Cần phân biệt biển số của xe nào với xe nào
  └─ Voting phải THÔNG MINH để không nhầm lẫn
```

## 📦 Pipeline: From Capture to Violation Record

```
┌──────────────────────────────────────────────────────────────┐
│ ESP32-CAM: Multi-Shot Capture                                 │
│  └─ Chụp 5 ảnh liên tiếp (0s, 1s, 2s, 3s, 4s)                │
└──────────────────────────────────────────┬───────────────────┘
                                            │ HTTP POST
┌──────────────────────────────────────────▼───────────────────┐
│ BACKEND: Frame-by-Frame Processing                            │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Step 1: YOLO Vehicle + Plate Detection                  │ │
│  │  └─ Mỗi frame → Detect tất cả xe + biển số             │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Step 2: OCR trên từng biển số                           │ │
│  │  └─ Extract text từ mỗi plate crop                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Step 3: Multi-Frame Tracking (SORT/DeepSORT)            │ │
│  │  └─ Track cùng 1 xe qua nhiều frame                     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Step 4: Voting Per Vehicle                              │ │
│  │  └─ Mỗi track_id → Vote OCR results                     │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ Step 5: Create Violation Records                        │ │
│  │  └─ Mỗi track_id → 1 record unique                      │ │
│  └─────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

## 🔍 Step 1: YOLO Detection

### Model: YOLOv5 (2 stages)

**Stage 1: Vehicle Detection**
```python
# Model: yolov5s.pt or custom trained model
# Classes: car, truck, motorcycle, bus

results = model_vehicle(image)
vehicles = []

for det in results.xyxy[0]:  # [x1, y1, x2, y2, conf, class]
    if det[5] in [2, 3, 5, 7]:  # car, motorcycle, bus, truck
        vehicles.append({
            "bbox": [int(det[0]), int(det[1]), int(det[2]), int(det[3])],
            "confidence": float(det[4]),
            "class": int(det[5])
        })
```

**Stage 2: License Plate Detection**
```python
# Model: custom YOLOv5 trained on license plates
# Input: Crop xe từ Stage 1

plates = []

for vehicle in vehicles:
    # Crop vehicle region
    x1, y1, x2, y2 = vehicle["bbox"]
    vehicle_crop = image[y1:y2, x1:x2]
    
    # Detect plate trong vehicle crop
    plate_results = model_plate(vehicle_crop)
    
    for plate_det in plate_results.xyxy[0]:
        # Convert coordinates về original image
        px1 = x1 + int(plate_det[0])
        py1 = y1 + int(plate_det[1])
        px2 = x1 + int(plate_det[2])
        py2 = y1 + int(plate_det[3])
        
        plates.append({
            "vehicle_id": vehicle["id"],
            "bbox": [px1, py1, px2, py2],
            "confidence": float(plate_det[4])
        })
```

## 🔤 Step 2: OCR (Optical Character Recognition)

### Option A: PaddleOCR (Recommended for Vietnamese)

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=True)

def perform_ocr(plate_crop):
    """
    OCR biển số xe
    
    Returns:
        {
            "text": "51F12345",
            "confidence": 0.92,
            "bbox": [[x1,y1], [x2,y2], ...]
        }
    """
    results = ocr.ocr(plate_crop, cls=True)
    
    if not results or not results[0]:
        return {"text": None, "confidence": 0.0}
    
    # PaddleOCR returns list of (bbox, (text, confidence))
    all_text = []
    all_conf = []
    
    for line in results[0]:
        text = line[1][0]
        conf = line[1][1]
        all_text.append(text)
        all_conf.append(conf)
    
    # Concatenate text, average confidence
    final_text = "".join(all_text).replace(" ", "")
    final_conf = sum(all_conf) / len(all_conf) if all_conf else 0.0
    
    # Post-process: Remove non-alphanumeric
    final_text = re.sub(r'[^A-Z0-9]', '', final_text.upper())
    
    return {
        "text": final_text if final_text else None,
        "confidence": round(final_conf, 4)
    }
```

### Option B: EasyOCR

```python
import easyocr

reader = easyocr.Reader(['en'], gpu=True)

def perform_ocr_easy(plate_crop):
    results = reader.readtext(plate_crop)
    
    if not results:
        return {"text": None, "confidence": 0.0}
    
    # results: [(bbox, text, confidence), ...]
    all_text = "".join([r[1] for r in results])
    avg_conf = sum([r[2] for r in results]) / len(results)
    
    final_text = re.sub(r'[^A-Z0-9]', '', all_text.upper())
    
    return {
        "text": final_text if final_text else None,
        "confidence": round(avg_conf, 4)
    }
```

## 🎯 Step 3: Multi-Frame Tracking (CRITICAL!)

### Vấn Đề: Phân Biệt Xe A vs Xe B

**Không tracking**:
```
Frame 1: OCR → 51F12345 (Xe A)
Frame 2: OCR → 51F12345 (Xe A), 29B98765 (Xe B)
Frame 3: OCR → 29B98765 (Xe B)

→ Làm sao biết "51F12345" ở Frame 1 và Frame 2 là CÙNG 1 XE?
```

### Giải Pháp: Object Tracking

**SORT (Simple Online Realtime Tracking)**:
```python
from sort import Sort

tracker = Sort(max_age=3, min_hits=2, iou_threshold=0.3)

# Mỗi frame
detections = np.array([[x1, y1, x2, y2, confidence], ...])
tracked_objects = tracker.update(detections)

# tracked_objects: [[x1, y1, x2, y2, track_id], ...]
```

**DeepSORT (với appearance features)** - BETTER:
```python
from deep_sort import DeepSort

tracker = DeepSort(model_path="ckpt.t7", max_age=30)

# Mỗi frame
outputs = tracker.update(detections, image)
# outputs: [[x1, y1, x2, y2, track_id, class], ...]
```

### Implementation

```python
class VehicleTracker:
    def __init__(self):
        self.tracker = Sort(max_age=5, min_hits=2)
        self.track_ocr_history = {}  # {track_id: [ocr_results]}
    
    def process_frame(self, image, frame_id):
        """
        Process 1 frame:
          1. Detect vehicles + plates
          2. Update tracker
          3. Run OCR
          4. Store OCR results per track_id
        """
        # Step 1: YOLO detect
        vehicles = detect_vehicles(image)
        
        # Step 2: Convert to SORT format
        detections = []
        for v in vehicles:
            x1, y1, x2, y2 = v["bbox"]
            conf = v["confidence"]
            detections.append([x1, y1, x2, y2, conf])
        
        detections = np.array(detections) if detections else np.empty((0, 5))
        
        # Step 3: Update tracker
        tracked = self.tracker.update(detections)
        
        # Step 4: For each tracked vehicle, detect plate + OCR
        for track in tracked:
            x1, y1, x2, y2, track_id = track[:5]
            track_id = int(track_id)
            
            # Crop vehicle
            vehicle_crop = image[int(y1):int(y2), int(x1):int(x2)]
            
            # Detect plates in vehicle
            plates = detect_plates_in_vehicle(vehicle_crop)
            
            for plate in plates:
                # Crop plate
                px1, py1, px2, py2 = plate["bbox"]
                plate_crop = vehicle_crop[py1:py2, px1:px2]
                
                # OCR
                ocr_result = perform_ocr(plate_crop)
                
                # Store history
                if track_id not in self.track_ocr_history:
                    self.track_ocr_history[track_id] = []
                
                self.track_ocr_history[track_id].append({
                    "frame_id": frame_id,
                    "license_plate": ocr_result["text"],
                    "confidence": ocr_result["confidence"],
                    "bbox": plate["bbox"]
                })
```

## 🗳️ Step 4: Voting Per Vehicle

**Mỗi `track_id` → Vote OCR results riêng**

```python
def vote_per_vehicle(track_ocr_history: dict) -> dict:
    """
    Vote OCR results cho từng xe
    
    Args:
        track_ocr_history: {track_id: [ocr_results]}
    
    Returns:
        {track_id: {plate, vote_count, confidence}}
    """
    voted_results = {}
    
    for track_id, ocr_list in track_ocr_history.items():
        # Filter out None
        valid_ocr = [o for o in ocr_list if o["license_plate"]]
        
        if not valid_ocr:
            voted_results[track_id] = None
            continue
        
        # Count votes
        from collections import Counter
        plates = [o["license_plate"] for o in valid_ocr]
        vote_counts = Counter(plates)
        
        # Winner
        winner_plate, vote_count = vote_counts.most_common(1)[0]
        
        # Avg confidence
        matching = [o for o in valid_ocr if o["license_plate"] == winner_plate]
        avg_conf = sum(o["confidence"] for o in matching) / len(matching)
        
        voted_results[track_id] = {
            "license_plate": winner_plate,
            "vote_count": vote_count,
            "total_frames": len(valid_ocr),
            "vote_percent": round(vote_count / len(valid_ocr) * 100, 2),
            "avg_confidence": round(avg_conf, 4)
        }
    
    return voted_results
```

### Ví Dụ Thực Tế

**Input**: 5 frames, 2 xe

```python
track_ocr_history = {
    # Xe A (track_id=1)
    1: [
        {"frame_id": 0, "license_plate": "51F12345", "confidence": 0.85},
        {"frame_id": 1, "license_plate": "51F12345", "confidence": 0.92},
        {"frame_id": 2, "license_plate": "51F1234S", "confidence": 0.78},  # Sai
        {"frame_id": 3, "license_plate": "51F12345", "confidence": 0.88}
    ],
    
    # Xe B (track_id=2)
    2: [
        {"frame_id": 1, "license_plate": "29B98765", "confidence": 0.81},
        {"frame_id": 2, "license_plate": "29B98765", "confidence": 0.89},
        {"frame_id": 3, "license_plate": "29B9876S", "confidence": 0.72},  # Sai
        {"frame_id": 4, "license_plate": "29B98765", "confidence": 0.86}
    ]
}
```

**Output**:
```python
{
    1: {
        "license_plate": "51F12345",
        "vote_count": 3,
        "total_frames": 4,
        "vote_percent": 75.0,
        "avg_confidence": 0.8833
    },
    2: {
        "license_plate": "29B98765",
        "vote_count": 3,
        "total_frames": 4,
        "vote_percent": 75.0,
        "avg_confidence": 0.8533
    }
}
```

## 📝 Step 5: Create Violation Records

**1 track_id → 1 violation record**

```python
async def create_violations_from_tracking(
    voted_results: dict,
    camera_id: int,
    timestamp: datetime,
    images: List[np.ndarray]
):
    """
    Tạo violation records từ voted results
    """
    violations = []
    
    for track_id, result in voted_results.items():
        if not result:
            continue
        
        # Filter: Chỉ tạo record nếu vote đủ mạnh
        if result["vote_count"] < 2:  # Ít nhất 2 phiếu
            continue
        
        if result["vote_percent"] < 40:  # Ít nhất 40%
            continue
        
        # Find best frame cho track này
        best_frame = find_best_frame_for_track(track_id, images)
        
        # Save images
        full_img_path = save_image(best_frame, "original")
        plate_crop_path = save_plate_crop(best_frame, result)
        
        # Create violation record
        violation = await db.violations.create({
            "camera_id": camera_id,
            "license_plate": result["license_plate"],
            "confidence": result["avg_confidence"],
            "image_url": full_img_path,
            "plate_image_url": plate_crop_path,
            "traffic_light_state": "red",
            "timestamp": timestamp,
            "metadata": {
                "track_id": track_id,
                "vote_count": result["vote_count"],
                "vote_percent": result["vote_percent"]
            }
        })
        
        violations.append(violation)
    
    return violations
```

## 🧠 Advanced: Fuzzy Matching cho OCR

**Vấn đề**: OCR đôi khi nhầm ký tự tương tự

```
Thực tế:  51F12345
OCR nhầm: 51F1234S  (5 → S)
          51F1Z345  (2 → Z)
          51F12B45  (3 → B)
```

**Giải pháp**: Levenshtein Distance

```python
from Levenshtein import distance as levenshtein_distance

def fuzzy_vote_license_plates(ocr_results: List[str], threshold=2):
    """
    Vote với fuzzy matching
    
    threshold: Số ký tự khác nhau tối đa để coi là "gần giống"
    """
    if not ocr_results:
        return None
    
    # Group plates theo fuzzy similarity
    groups = []
    
    for plate in ocr_results:
        # Tìm group phù hợp
        found_group = False
        for group in groups:
            # So sánh với representative của group
            if levenshtein_distance(plate, group[0]) <= threshold:
                group.append(plate)
                found_group = True
                break
        
        if not found_group:
            groups.append([plate])
    
    # Group lớn nhất thắng
    largest_group = max(groups, key=len)
    
    # Chọn plate xuất hiện nhiều nhất trong group
    from collections import Counter
    winner = Counter(largest_group).most_common(1)[0][0]
    
    return {
        "license_plate": winner,
        "vote_count": len(largest_group),
        "total": len(ocr_results),
        "vote_percent": round(len(largest_group) / len(ocr_results) * 100, 2)
    }


# Ví dụ
ocr_results = ["51F12345", "51F12345", "51F1234S", "51F12B45"]

result = fuzzy_vote_license_plates(ocr_results, threshold=1)
# → "51F12345" (vì 4 chuỗi đều gần giống nhau)
```

## ✅ Complete Pipeline Example

```python
class TrafficViolationDetector:
    def __init__(self):
        self.vehicle_model = load_yolo_model("yolov5s.pt")
        self.plate_model = load_yolo_model("plate_detector.pt")
        self.ocr = PaddleOCR(lang='en')
        self.tracker = Sort()
        self.track_ocr_history = {}
    
    async def process_multi_frame(
        self,
        images: List[np.ndarray],
        camera_id: int,
        timestamp: datetime
    ):
        """
        Process multiple frames và tạo violations
        """
        # Process từng frame
        for i, image in enumerate(images):
            self.process_single_frame(image, frame_id=i)
        
        # Vote results
        voted_results = vote_per_vehicle(self.track_ocr_history)
        
        # Create violations
        violations = await create_violations_from_tracking(
            voted_results,
            camera_id,
            timestamp,
            images
        )
        
        print(f"✅ Created {len(violations)} violations from {len(images)} frames")
        
        return violations
    
    def process_single_frame(self, image, frame_id):
        # Detect vehicles
        vehicles = self.vehicle_model(image)
        
        # Update tracker
        detections = self.vehicles_to_detections(vehicles)
        tracked = self.tracker.update(detections)
        
        # For each track, detect plate + OCR
        for track in tracked:
            track_id = int(track[4])
            bbox = track[:4]
            
            # Detect plates
            plates = self.detect_plates_in_bbox(image, bbox)
            
            # OCR
            for plate in plates:
                ocr_result = self.perform_ocr(plate["crop"])
                
                if track_id not in self.track_ocr_history:
                    self.track_ocr_history[track_id] = []
                
                self.track_ocr_history[track_id].append({
                    "frame_id": frame_id,
                    "license_plate": ocr_result["text"],
                    "confidence": ocr_result["confidence"]
                })
```

---

## 🎯 Summary: Chiến Lược Tổng Thể

```
5 Frames → YOLO (vehicles + plates)
         → Tracking (SORT/DeepSORT)
         → OCR per frame
         → Vote PER TRACK_ID
         → 1 track_id = 1 violation
```

**Key Points**:
1. ✅ **Tracking là QUAN TRỌNG NHẤT** - Phân biệt xe khác nhau
2. ✅ **Vote theo track_id**, không vote chung tất cả
3. ✅ **Fuzzy matching** để xử lý OCR errors
4. ✅ **Quality filtering** trước khi vote
5. ✅ **Minimum vote threshold** (40-50%) để đảm bảo độ tin cậy
