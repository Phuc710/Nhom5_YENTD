"""
IMAGE PROCESSOR

Pipeline thật:
1. Load ảnh từ camera/webcam
2. Detect vehicle / plate bằng YOLO
3. Crop vùng plate
4. Preprocess bằng OpenCV
5. OCR bằng EasyOCR
6. Lưu ảnh thật + ghi DB
"""

import argparse
import logging
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import easyocr
import numpy as np
import requests
from ultralytics import YOLO


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ImageProcessor")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "traffic_ai.db"
UPLOADS_DIR = BASE_DIR.parent / "imge"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PLATE_CAPTURE_DIR = UPLOADS_DIR / "plates"
PLATE_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
BACKEND_URL = (os.getenv("AI_BACKEND_URL") or os.getenv("BACKEND_URL") or "http://127.0.0.1:5050").strip()
BACKEND_TOKEN = (os.getenv("AI_BACKEND_TOKEN") or os.getenv("DASHBOARD_SECRET") or "TRAFFIC_AI_TOKEN").strip()

PLATE_CLASS_HINTS = {
    "license plate",
    "licence plate",
    "license_plate",
    "licence_plate",
    "number plate",
    "number_plate",
    "plate",
}
VEHICLE_CLASS_HINTS = {"car", "motorcycle", "motorbike", "bus", "truck"}
PLATE_PATTERNS = [
    r"^\d{2}[A-Z]\d{4,6}$",
    r"^\d{2}[A-Z]\d[A-Z0-9]{4,6}$",
    r"^\d{2}[A-Z]{1,2}\d{4,6}$",
]


def resolve_model_path() -> Path:
    candidates = [
        BASE_DIR / "traffic_yolov8n_best.pt",
        BASE_DIR / "yolov8n.pt",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[-1]


class ImageProcessor:
    def __init__(self, db_path=DB_PATH):
        self.db_path = Path(db_path)
        self.violation_count = 0
        self.model_path = resolve_model_path()
        self.model = YOLO(str(self.model_path))
        self.ocr_reader = easyocr.Reader(["en"], gpu=False)
        log.info("YOLO model: %s", self.model_path.name)

    def get_db(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def get_reference_rows(self):
        rows = []
        conn = self.get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT plate_text, vehicle_type, light_state, violation_time, full_image_path,
                       plate_image_path, camera_id, plate_confidence, speed_kmh
                FROM violations
                WHERE status!='DELETED' AND plate_text!=''
                ORDER BY violation_ts DESC
                LIMIT 200
                """
            )
            for row in cur.fetchall():
                rows.append(
                    {
                        "plate_text": row["plate_text"],
                        "vehicle_type": row["vehicle_type"] or "",
                        "light_state": row["light_state"] or "",
                        "violation_time": row["violation_time"] or "",
                        "full_image_path": row["full_image_path"] or "",
                        "plate_image_path": row["plate_image_path"] or row["full_image_path"] or "",
                        "camera_id": row["camera_id"] or "",
                        "plate_confidence": str(row["plate_confidence"] or 0.0),
                        "speed_kmh": str(row["speed_kmh"] or 0.0),
                        "source": "image_processor.py",
                    }
                )
        except Exception as e:
            log.error("get_reference_rows: %s", e)
        finally:
            conn.close()
        return rows

    def save_image_file(self, image_path_input, output_dir, filename):
        try:
            input_path = Path(image_path_input)
            if not input_path.exists():
                log.warning("Image file not found: %s", input_path)
                return None
            output_path = output_dir / filename
            shutil.copy2(input_path, output_path)
            rel_path = f"/imge/{filename}"
            log.info("Saved: %s", rel_path)
            return rel_path
        except Exception as e:
            log.error("Failed to save image: %s", e)
            return None

    def _pick_detections(self, image: np.ndarray):
        plate_box = None
        vehicle_box = None
        vehicle_type = "UNKNOWN"
        vehicle_conf = 0.0
        best_plate_conf = -1.0
        best_vehicle_conf = -1.0

        results = self.model(image, verbose=False)[0]
        for box in results.boxes:
            cls_id = int(box.cls[0])
            cls_name = str(self.model.names.get(cls_id, cls_id)).lower().strip()
            conf = float(box.conf[0])
            coords = [int(v) for v in box.xyxy[0].tolist()]

            if cls_name in PLATE_CLASS_HINTS and conf > best_plate_conf:
                plate_box = coords
                best_plate_conf = conf

            if cls_name in VEHICLE_CLASS_HINTS and conf > best_vehicle_conf:
                vehicle_box = coords
                best_vehicle_conf = conf
                vehicle_type = "MOTORBIKE" if cls_name in {"motorcycle", "motorbike"} else "CAR"
                vehicle_conf = conf

        return vehicle_box, vehicle_type, vehicle_conf, plate_box, best_plate_conf

    def _crop_plate_from_vehicle(self, image: np.ndarray, vehicle_box):
        h, w = image.shape[:2]
        if not vehicle_box:
            return None, None
        x1, y1, x2, y2 = vehicle_box
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)
        vw = max(1, x2 - x1)
        vh = max(1, y2 - y1)
        crop_x1 = max(0, x1 + int(vw * 0.18))
        crop_x2 = min(w, x2 - int(vw * 0.18))
        crop_y1 = max(0, y1 + int(vh * 0.55))
        crop_y2 = min(h, y1 + int(vh * 0.92))
        if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
            return None, None
        return image[crop_y1:crop_y2, crop_x1:crop_x2], [crop_x1, crop_y1, crop_x2, crop_y2]

    def _preprocess_plate(self, plate_crop: np.ndarray):
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        denoise = cv2.bilateralFilter(gray, 7, 50, 50)
        sharp_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        sharp = cv2.filter2D(denoise, -1, sharp_kernel)
        adaptive = cv2.adaptiveThreshold(
            sharp, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
        )
        _, otsu = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants = [gray, sharp, adaptive, otsu]
        out = [plate_crop]
        for variant in variants:
            resized = cv2.resize(variant, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            out.append(cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR))
        return out

    def _normalize_plate(self, text: str) -> str:
        return normalize_plate_text(text)

    def _ocr_plate(self, plate_crop: np.ndarray):
        best_text = ""
        best_conf = 0.0
        for variant in self._preprocess_plate(plate_crop):
            try:
                results = self.ocr_reader.readtext(variant, detail=1, paragraph=False, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.")
            except Exception:
                results = []
            for item in results:
                if len(item) < 3:
                    continue
                text = self._normalize_plate(item[1])
                conf = float(item[2] or 0.0)
                if text and conf > best_conf:
                    best_text = text
                    best_conf = conf
        return best_text, best_conf

    def detect_vehicle_and_plate_frame_with_meta(self, image: np.ndarray):
        try:
            if image is None:
                return {
                    "image": None,
                    "vehicle_crop": None,
                    "plate_crop": None,
                    "vehicle_type": "UNKNOWN",
                    "vehicle_conf": 0.0,
                    "plate_text": "",
                    "normalized_plate_text": "",
                    "confidence": 0.0,
                    "vehicle_box": None,
                    "plate_box": None,
                    "frame_shape": None,
                }

            vehicle_box, vehicle_type, vehicle_conf, plate_box, plate_conf = self._pick_detections(image)
            vehicle_crop = None
            if vehicle_box:
                vx1, vy1, vx2, vy2 = vehicle_box
                ih, iw = image.shape[:2]
                vx1 = max(0, min(iw - 1, vx1))
                vy1 = max(0, min(ih - 1, vy1))
                vx2 = max(vx1 + 1, min(iw, vx2))
                vy2 = max(vy1 + 1, min(ih, vy2))
                vehicle_crop = image[vy1:vy2, vx1:vx2]

            plate_crop = None
            if plate_box:
                x1, y1, x2, y2 = plate_box
                plate_crop = image[max(0, y1):max(y1 + 1, y2), max(0, x1):max(x1 + 1, x2)]
            elif vehicle_box:
                plate_crop, plate_box = self._crop_plate_from_vehicle(image, vehicle_box)

            if plate_crop is None or plate_crop.size == 0:
                return {
                    "image": image,
                    "vehicle_crop": vehicle_crop,
                    "plate_crop": None,
                    "vehicle_type": vehicle_type,
                    "vehicle_conf": vehicle_conf,
                    "plate_text": "",
                    "normalized_plate_text": "",
                    "confidence": 0.0,
                    "vehicle_box": vehicle_box,
                    "plate_box": plate_box,
                    "frame_shape": image.shape[:2],
                }

            plate_text, ocr_conf = self._ocr_plate(plate_crop)
            plate_norm = self._normalize_plate(plate_text)
            return {
                "image": image,
                "vehicle_crop": vehicle_crop,
                "plate_crop": plate_crop,
                "vehicle_type": vehicle_type,
                "vehicle_conf": vehicle_conf,
                "plate_text": plate_text,
                "normalized_plate_text": plate_norm,
                "confidence": max(ocr_conf, plate_conf, 0.0),
                "vehicle_box": vehicle_box,
                "plate_box": plate_box,
                "frame_shape": image.shape[:2],
            }
        except Exception as e:
            log.error("Detection failed: %s", e)
            return {
                "image": None,
                "vehicle_crop": None,
                "plate_crop": None,
                "vehicle_type": "UNKNOWN",
                "vehicle_conf": 0.0,
                "plate_text": "",
                "normalized_plate_text": "",
                "confidence": 0.0,
                "vehicle_box": None,
                "plate_box": None,
                "frame_shape": None,
            }

    def detect_vehicle_and_plate_frame(self, image: np.ndarray):
        meta = self.detect_vehicle_and_plate_frame_with_meta(image)
        return (
            meta["image"],
            meta["plate_crop"],
            meta["vehicle_type"],
            meta["vehicle_conf"],
            meta["plate_text"],
            meta["confidence"],
        )

    def build_violation_detection(self, image: np.ndarray) -> dict:
        meta = self.detect_vehicle_and_plate_frame_with_meta(image)
        plate_text = (meta.get("plate_text") or "").strip()
        plate_norm = (meta.get("normalized_plate_text") or normalize_plate_text(plate_text)).strip()
        return {
            "frame": meta.get("image"),
            "vehicle_crop": meta.get("vehicle_crop"),
            "plate_crop": meta.get("plate_crop"),
            "vehicle_type": meta.get("vehicle_type") or "UNKNOWN",
            "vehicle_confidence": float(meta.get("vehicle_conf") or 0.0),
            "vehicle_box": meta.get("vehicle_box"),
            "plate_box": meta.get("plate_box"),
            "ocr_text_raw": plate_text,
            "plate_number": plate_text,
            "normalized_plate_number": plate_norm,
            "ocr_confidence": float(meta.get("confidence") or 0.0),
            "frame_shape": meta.get("frame_shape"),
        }

    def detect_vehicle_and_plate(self, image_path):
        image = cv2.imread(str(image_path))
        return self.detect_vehicle_and_plate_frame(image)

    def save_violation_to_db(
        self,
        plate_text,
        plate_confidence,
        vehicle_type,
        vehicle_confidence,
        light_state,
        full_image_path,
        plate_image_path,
        camera_id="CAM_01",
        esp32_id="ESP32_MAIN",
        speed_kmh=0.0,
    ):
        payload = {
            "camera_code": str(camera_id or "").strip() or "CAM_01",
            "plate_number": plate_text or "",
            "normalized_plate_number": normalize_plate_text(plate_text or ""),
            "violation_type": "red_light_crossing",
            "violation_time": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "full_image_url": full_image_path,
            "vehicle_crop_url": full_image_path,
            "plate_crop_url": plate_image_path or full_image_path,
            "light_state": str(light_state or "RED"),
            "ocr_text_raw": plate_text or "",
            "ocr_confidence": float(plate_confidence or 0.0),
            "vehicle_type": vehicle_type or "UNKNOWN",
            "status": "new",
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BACKEND_TOKEN}",
        }
        try:
            r = requests.post(
                f"{BACKEND_URL.rstrip('/')}/api/violations",
                json=payload,
                headers=headers,
                timeout=5,
            )
            if r.status_code >= 300:
                log.error("Failed to save via backend: HTTP %s %s", r.status_code, r.text[:200])
                return None
            body = r.json() if r.content else {}
            violation_id = (
                (body.get("violation") or {}).get("id")
                if isinstance(body, dict)
                else None
            )
            self.violation_count += 1
            log.info("Saved violation via backend ID=%s: %s", violation_id, plate_text)
            return violation_id
        except Exception as e:
            log.error("Failed to save via backend: %s", e)
            return None

    def _get_next_violation_id(self):
        try:
            conn = self.get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(id) FROM violations")
            result = cursor.fetchone()[0]
            conn.close()
            return (result or 0) + 1
        except Exception:
            return 1

    def process_image(self, image_path, light_state="RED", camera_id="CAM_01"):
        log.info("Processing: %s", image_path)
        log.info("Light: %s | Camera: %s", light_state, camera_id)

        if not Path(image_path).exists():
            log.error("Image not found: %s", image_path)
            return None
        if light_state != "RED":
            log.warning("Light is %s - skipping (only process RED)", light_state)
            return None

        _, plate_crop, vtype, vconf, plate, pconf = self.detect_vehicle_and_plate(image_path)
        if not plate:
            log.warning("OCR did not produce a readable plate")
            return None

        violation_id = self._get_next_violation_id()
        safe_plate = "".join(ch if ch.isalnum() else "_" for ch in plate).strip("_") or f"VIOLATION_{violation_id}"
        ts = int(datetime.now().timestamp())
        full_filename = f"{safe_plate}_{ts}.jpg"
        plate_filename = f"{safe_plate}_{ts}_plate.jpg"
        full_url = self.save_image_file(image_path, UPLOADS_DIR, full_filename)
        plate_url = full_url
        if plate_crop is not None and getattr(plate_crop, "size", 0):
            plate_path = PLATE_CAPTURE_DIR / plate_filename
            if cv2.imwrite(str(plate_path), plate_crop, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                plate_url = f"/imge/plates/{plate_filename}"
        if not full_url:
            return None

        return self.save_violation_to_db(
            plate_text=plate,
            plate_confidence=pconf,
            vehicle_type=vtype or "UNKNOWN",
            vehicle_confidence=vconf,
            light_state=light_state,
            full_image_path=full_url,
            plate_image_path=plate_url,
            camera_id=camera_id,
            speed_kmh=0.0,
        )

    def process_batch(self, image_dir, light_state="RED", camera_id="CAM_01"):
        image_dir = Path(image_dir)
        if not image_dir.exists():
            log.error("Directory not found: %s", image_dir)
            return 0
        images = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            images.extend(image_dir.glob(ext))
        log.info("Found %d images in %s", len(images), image_dir)
        success = 0
        for image_path in images:
            if self.process_image(str(image_path), light_state=light_state, camera_id=camera_id):
                success += 1
        log.info("Processed: %d/%d images", success, len(images))
        return success


def main():
    parser = argparse.ArgumentParser(description="Process images -> detect -> OCR -> save DB")
    parser.add_argument("image_path", help="Image file or directory path")
    parser.add_argument("--light", default="RED", choices=["RED", "YELLOW", "GREEN"])
    parser.add_argument("--camera", default="CAM_01")
    parser.add_argument("--batch", action="store_true")
    args = parser.parse_args()

    log.info("=" * 70)
    log.info("IMAGE PROCESSOR - Real-time Violation Detection")
    log.info("=" * 70)

    processor = ImageProcessor()
    image_path = Path(args.image_path)
    if args.batch or image_path.is_dir():
        processor.process_batch(image_path, light_state=args.light, camera_id=args.camera)
    else:
        processor.process_image(str(image_path), light_state=args.light, camera_id=args.camera)


_PROCESSOR_SINGLETON = None


def normalize_plate_text(text: str) -> str:
    if not text:
        return ""
    text = (text or "").upper().strip()
    text = text.replace(" ", "").replace(".", "").replace("_", "-")
    replace_map = {"O": "0", "I": "1", "L": "1", "Z": "2", "S": "5"}
    fixed = []
    for ch in text:
        fixed.append(replace_map.get(ch, ch))
    text = "".join(fixed)
    text = "".join(ch for ch in text if ch.isalnum())
    return text


def is_possible_vn_plate(text: str) -> bool:
    candidate = normalize_plate_text(text)
    return any(__import__("re").match(pattern, candidate) for pattern in PLATE_PATTERNS)


def blur_score(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def brightness_score(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(gray.mean())


def glare_ratio(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray > 245))


def center_alignment_score(frame_shape, box) -> tuple[float, float]:
    if not frame_shape or not box:
        return 999.0, 0.0
    h, w = frame_shape
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    dx = abs(cx - (w / 2.0)) / max(1.0, w / 2.0)
    dy = abs(cy - (h * 0.68)) / max(1.0, h * 0.32)
    offset = float((dx * dx + dy * dy) ** 0.5)
    area_ratio = float(max(0, x2 - x1) * max(0, y2 - y1) / max(1, w * h))
    return offset, area_ratio


def _get_processor() -> ImageProcessor:
    global _PROCESSOR_SINGLETON
    if _PROCESSOR_SINGLETON is None:
        _PROCESSOR_SINGLETON = ImageProcessor()
    return _PROCESSOR_SINGLETON


def _format_display_plate(canon: str) -> str:
    if len(canon) >= 8:
        return f"{canon[:4]} {canon[4:7]}.{canon[7:]}" if len(canon) >= 9 else f"{canon[:4]}-{canon[4:]}"
    return canon


def _save_plate_capture(plate_crop: np.ndarray, plate_norm: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_plate = plate_norm or "UNKNOWN"
    path = PLATE_CAPTURE_DIR / f"{safe_plate}_{ts}.jpg"
    cv2.imwrite(str(path), plate_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return f"/imge/plates/{path.name}"


def _match_reference(plate_norm: str, reference_rows: Optional[list[dict]] = None) -> Optional[dict]:
    canon = normalize_plate_text(plate_norm)
    rows = reference_rows or _get_processor().get_reference_rows()
    for row in rows:
        plate = row.get("plate_text") or row.get("plate") or ""
        if normalize_plate_text(plate) == canon:
            return row
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, plate_text, vehicle_type, light_state, speed_kmh, violation_time,
                   full_image_path, plate_image_path, notes
            FROM violations
            WHERE REPLACE(REPLACE(REPLACE(UPPER(COALESCE(plate_text,'')),'-',''),' ',''),'.','') = ?
            ORDER BY violation_ts DESC
            LIMIT 1
            """,
            (canon,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def process_snapshot_and_match(frame: np.ndarray, reference_rows: Optional[list[dict]] = None) -> dict:
    processor = _get_processor()
    meta = processor.detect_vehicle_and_plate_frame_with_meta(frame)
    image = meta["image"]
    plate_crop = meta["plate_crop"]
    vehicle_type = meta["vehicle_type"]
    vehicle_conf = meta["vehicle_conf"]
    plate_text = meta["plate_text"]
    det_conf = meta["confidence"]
    plate_box = meta["plate_box"]
    frame_shape = meta["frame_shape"]
    if plate_crop is None or plate_crop.size == 0:
        return {
            "ok": False,
            "matched": False,
            "message": "Không tìm thấy biển số. Quý khách vui lòng chụp lại.",
            "needs_recapture": True,
        }

    center_offset, area_ratio = center_alignment_score(frame_shape, plate_box)
    if center_offset > 0.68 or area_ratio < 0.008:
        shot = _save_plate_capture(plate_crop, "CENTER")
        return {
            "ok": False,
            "matched": False,
            "snapshot_url": shot,
            "message": "Bien so dang qua lech hoac con qua nho trong khung hinh. Quy khach vui long dua camera gan hon va chup lai.",
            "needs_recapture": True,
            "center_offset": center_offset,
            "plate_area_ratio": area_ratio,
        }

    if blur_score(plate_crop) < 90:
        shot = _save_plate_capture(plate_crop, "BLUR")
        return {
            "ok": False,
            "matched": False,
            "snapshot_url": shot,
            "message": "Ảnh biển số bị mờ. Quý khách vui lòng chụp lại.",
            "needs_recapture": True,
        }

    bright = brightness_score(plate_crop)
    glare = glare_ratio(plate_crop)
    if bright < 70 or bright > 210 or glare > 0.22:
        shot = _save_plate_capture(plate_crop, "LIGHT")
        return {
            "ok": False,
            "matched": False,
            "snapshot_url": shot,
            "message": "Anh sang chua phu hop hoac bi loa. Quy khach vui long giu on dinh va chup lai.",
            "needs_recapture": True,
        }

    plate_norm = normalize_plate_text(plate_text)
    confidence = float(det_conf or 0.0)
    shot = _save_plate_capture(plate_crop, plate_norm or "UNKNOWN")

    if not plate_norm or confidence < 0.8 or not is_possible_vn_plate(plate_norm):
        return {
            "ok": False,
            "matched": False,
            "snapshot_url": shot,
            "confidence": confidence,
            "message": "Không nhận diện chắc chắn. Quý khách vui lòng chụp lại.",
            "needs_recapture": True,
        }

    matched = _match_reference(plate_norm, reference_rows)
    if not matched:
        return {
            "ok": False,
            "matched": False,
            "snapshot_url": shot,
            "plate_text": plate_norm,
            "display_plate": _format_display_plate(plate_norm),
            "confidence": confidence,
            "message": "Biển số chưa có trong dữ liệu hệ thống. Quý khách vui lòng chụp lại.",
            "needs_recapture": True,
        }

    display_plate = matched.get("plate_text") or matched.get("plate") or _format_display_plate(plate_norm)
    violation = {
        "id": matched.get("id"),
        "plate": display_plate,
        "vehicle_type": matched.get("vehicle_type") or vehicle_type,
        "speed": matched.get("speed_kmh") or matched.get("speed") or 0,
        "light": matched.get("light_state") or matched.get("light") or "RED",
        "reason": matched.get("violation_reason") or matched.get("notes") or "Vượt vạch dừng khi đèn đỏ",
        "time": matched.get("violation_time") or matched.get("created_at") or "",
        "image_path": matched.get("plate_image_path") or matched.get("full_image_path") or shot,
    }
    return {
        "ok": True,
        "matched": True,
        "plate_text": plate_norm,
        "display_plate": display_plate,
        "confidence": confidence,
        "snapshot_url": shot,
        "vehicle_type": vehicle_type,
        "center_offset": center_offset,
        "plate_area_ratio": area_ratio,
        "violation": violation,
        "message": "Nhận diện thành công",
    }

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Cancelled by user")
        sys.exit(1)
    except Exception as e:
        log.error("Error: %s", e)
        raise
