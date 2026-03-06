# License Plate Detection với Tracking & Voting

## 🎯 Flow Thực Tế

```
5 Frames → YOLO (vehicles + plates) → Track (SORT) → OCR → Vote per track_id → Save
```

---

## 📦 Complete Pipeline

### 1. YOLO Detection

```python
# Stage 1: Vehicle detection
results = yolo_vehicle_model(image)
vehicles = results.xyxy[0]  # [x1, y1, x2, y2, conf, class]

# Stage 2: Plate detection trong vehicle crop
for vehicle in vehicles:
    x1, y1, x2, y2 = vehicle[:4]
    crop = image[int(y1):int(y2), int(x1):int(x2)]
    plates = yolo_plate_model(crop)
```

### 2. Object Tracking (SORT)

```python
from sort import Sort

tracker = Sort(max_age=5, min_hits=2)

class ViolationProcessor:
    def __init__(self):
        self.tracker = Sort()
        self.track_ocr_history = {}  # {track_id: [ocr_results]}
    
    def process_frame(self, image, frame_id):
        # YOLO detect
        vehicles = detect_vehicles(image)
        detections = np.array([[v['x1'], v['y1'], v['x2'], v['y2'], v['conf']] for v in vehicles])
        
        # Update tracker
        tracked_objects = self.tracker.update(detections)
        
        # OCR per tracked vehicle
        for track in tracked_objects:
            track_id = int(track[4])
            bbox = track[:4]
            
            # Detect plate
            plate_crop = detect_plate_in_bbox(image, bbox)
            if plate_crop is not None:
                # OCR
                ocr_result = perform_ocr(plate_crop)
                
                # Store
                if track_id not in self.track_ocr_history:
                    self.track_ocr_history[track_id] = []
                
                self.track_ocr_history[track_id].append({
                    "frame_id": frame_id,
                    "license_plate": ocr_result["text"],
                    "confidence": ocr_result["confidence"]
                })
```

### 3. OCR (PaddleOCR)

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=True)

def perform_ocr(plate_crop):
    results = ocr.ocr(plate_crop, cls=True)
    if not results or not results[0]:
        return {"text": None, "confidence": 0.0}
    
    text = "".join([line[1][0] for line in results[0]])
    conf = sum([line[1][1] for line in results[0]]) / len(results[0])
    
    # Cleanup
    text = re.sub(r'[^A-Z0-9]', '', text.upper())
    
    return {"text": text if text else None, "confidence": round(conf, 4)}
```

### 4. Voting Per Track

```python
from collections import Counter

def vote_per_vehicle(track_ocr_history):
    """
    Args: {track_id: [ocr_results]}
    Returns: {track_id: {plate, vote_count, confidence}}
    """
    voted = {}
    
    for track_id, ocr_list in track_ocr_history.items():
        valid = [o for o in ocr_list if o["license_plate"]]
        if not valid:
            continue
        
        plates = [o["license_plate"] for o in valid]
        winner, count = Counter(plates).most_common(1)[0]
        
        matching = [o for o in valid if o["license_plate"] == winner]
        avg_conf = sum(o["confidence"] for o in matching) / len(matching)
        
        voted[track_id] = {
            "license_plate": winner,
            "vote_count": count,
            "total_frames": len(valid),
            "vote_percent": round(count / len(valid) * 100, 2),
            "avg_confidence": round(avg_conf, 4)
        }
    
    return voted
```

---

## 🔧 Fuzzy Matching (Handle OCR Errors)

```python
from Levenshtein import distance

def fuzzy_vote(ocr_results, threshold=1):
    """Vote với fuzzy matching cho OCR errors"""
    if not ocr_results:
        return None
    
    groups = []
    for plate in [r["license_plate"] for r in ocr_results if r.get("license_plate")]:
        found = False
        for group in groups:
            if distance(plate, group[0]) <= threshold:
                group.append(plate)
                found = True
                break
        if not found:
            groups.append([plate])
    
    largest_group = max(groups, key=len)
    winner = Counter(largest_group).most_common(1)[0][0]
    
    return {
        "license_plate": winner,
        "vote_count": len(largest_group),
        "vote_percent": round(len(largest_group) / len(ocr_results) * 100, 2)
    }
```

---

## 💾 Save Violations

```python
async def create_violations(voted_results, camera_id, timestamp, images):
    violations = []
    
    for track_id, result in voted_results.items():
        # Filter: vote >= 40%
        if result["vote_count"] < 2 or result["vote_percent"] < 40:
            continue
        
        # Find best frame
        best_frame = images[0]  # hoặc chọn frame có quality cao nhất
        
        # Save images
        full_path = save_image(best_frame, f"original/cam{camera_id}_{timestamp}.jpg")
        plate_path = save_plate_crop(best_frame, result)
        
        # Create record
        violation = await db.violations.create({
            "camera_id": camera_id,
            "license_plate": result["license_plate"],
            "confidence": result["avg_confidence"],
            "full_image_url": full_path,
            "cropped_plate_url": plate_path,
            "timestamp": timestamp,
            "vote_count": result["vote_count"],
            "vote_percent": result["vote_percent"],
            "track_id": track_id
        })
        
        violations.append(violation)
    
    return violations
```

---

## ✅ Complete Flow

```python
async def process_multi_frame_violations(files: List[UploadFile], camera_id: int, timestamp):
    processor = ViolationProcessor()
    images = []
    
    # Process each frame
    for i, file in enumerate(files):
        img = cv2.imdecode(np.frombuffer(await file.read(), np.uint8), cv2.IMREAD_COLOR)
        images.append(img)
        processor.process_frame(img, frame_id=i)
    
    # Vote per vehicle
    voted_results = vote_per_vehicle(processor.track_ocr_history)
    
    # Save violations
    violations = await create_violations(voted_results, camera_id, timestamp, images)
    
    print(f"✅ Created {len(violations)} violations from {len(files)} frames")
    return violations
```

---

**Production Config**:
```python
VOTE_MIN_COUNT = 2
VOTE_MIN_PERCENT = 40
FUZZY_THRESHOLD = 1  # max 1 char difference
```
