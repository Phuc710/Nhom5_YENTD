"""
ImageService — Compress images to WebP and upload to Supabase Storage.

Pipeline for violation evidence (3 images):
  1. original  — Full frame (resized), NO overlay → raw legal evidence
  2. vehicle   — Crop xe + draw red bbox + plate text label
  3. plate     — Crop biển số, phóng to, yellow border

Why WebP?
  - 25-35% smaller than JPEG at same quality
  - cv2.imencode('.webp') natively supported — no extra deps
  - Typically < 10ms encode for 640x480

All methods are synchronous — wrap with asyncio.to_thread() in routes.
"""
import logging
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("trafficcam.image")

# ─── Drawing constants ─────────────────────────────────────────────────────
_BBOX_COLOR_VEHICLE = (0, 0, 220)     # Red (BGR) for vehicle box
_BBOX_COLOR_PLATE   = (0, 215, 255)   # Yellow (BGR) for plate border
_BBOX_THICKNESS     = 3
_LABEL_FONT         = cv2.FONT_HERSHEY_SIMPLEX
_LABEL_SCALE        = 0.7
_LABEL_THICKNESS    = 2
_LABEL_BG_COLOR     = (0, 0, 220)     # Red label background
_LABEL_FG_COLOR     = (255, 255, 255) # White text

# ─── WebP defaults ─────────────────────────────────────────────────────────
_DEFAULT_QUALITY    = 80
_DEFAULT_MAX_W      = 1280
_DEFAULT_MAX_H      = 720


# ---------------------------------------------------------------------------
# Pure image helpers (no class state needed)
# ---------------------------------------------------------------------------

def _resize_if_needed(img: np.ndarray, max_w: int, max_h: int) -> np.ndarray:
    """Downscale only if needed. Preserves aspect ratio."""
    h, w = img.shape[:2]
    if w <= max_w and h <= max_h:
        return img
    scale = min(max_w / w, max_h / h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _encode_webp(img: np.ndarray, quality: int = _DEFAULT_QUALITY) -> Optional[bytes]:
    """Encode BGR frame to WebP bytes."""
    params = [cv2.IMWRITE_WEBP_QUALITY, max(1, min(100, quality))]
    ok, buf = cv2.imencode(".webp", img, params)
    if not ok:
        # Fallback to JPEG if WebP fails
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else None


def _crop_bbox(
    frame: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    padding: int = 10,
) -> np.ndarray:
    """Crop region with padding, clamped to frame bounds."""
    h, w = frame.shape[:2]
    return frame[
        max(0, y1 - padding) : min(h, y2 + padding),
        max(0, x1 - padding) : min(w, x2 + padding),
    ]


def draw_vehicle_evidence(
    frame: np.ndarray,
    vehicle_bbox: Tuple[int, int, int, int],
    plate_text: Optional[str] = None,
    plate_bbox: Optional[Tuple[int, int, int, int]] = None,
    confidence: Optional[float] = None,
) -> np.ndarray:
    """
    Draw evidence overlay on a copy of the frame:
      - Red rectangle around vehicle
      - Red label with plate text + confidence above box
      - Yellow rectangle around license plate (if bbox provided)

    Returns a NEW numpy array (original is NOT modified).
    """
    vis = frame.copy()
    x1, y1, x2, y2 = vehicle_bbox

    # ── Vehicle bounding box ──────────────────────────────────────────
    cv2.rectangle(vis, (x1, y1), (x2, y2), _BBOX_COLOR_VEHICLE, _BBOX_THICKNESS)

    # ── Label above vehicle box ───────────────────────────────────────
    label_parts = []
    if plate_text:
        label_parts.append(plate_text)
    if confidence is not None:
        label_parts.append(f"{confidence:.0%}")
    label = "  ".join(label_parts) if label_parts else "Vi phạm"

    (lw, lh), baseline = cv2.getTextSize(label, _LABEL_FONT, _LABEL_SCALE, _LABEL_THICKNESS)
    label_x = max(0, x1)
    label_y = max(lh + baseline + 4, y1 - 6)

    # Label background rectangle
    cv2.rectangle(
        vis,
        (label_x, label_y - lh - baseline - 4),
        (label_x + lw + 8, label_y + 2),
        _LABEL_BG_COLOR,
        cv2.FILLED,
    )
    # Label text
    cv2.putText(
        vis, label,
        (label_x + 4, label_y - baseline),
        _LABEL_FONT, _LABEL_SCALE, _LABEL_FG_COLOR, _LABEL_THICKNESS, cv2.LINE_AA,
    )

    # ── Plate bounding box (yellow) ───────────────────────────────────
    if plate_bbox is not None:
        px1, py1, px2, py2 = plate_bbox
        cv2.rectangle(vis, (px1, py1), (px2, py2), _BBOX_COLOR_PLATE, 2)

    return vis


def draw_plate_crop(
    frame: np.ndarray,
    plate_bbox: Tuple[int, int, int, int],
    plate_text: Optional[str] = None,
    min_w: int = 200,
) -> np.ndarray:
    """
    Crop + enlarge license plate with yellow border and text label below.
    Mimics the image in the user screenshot: plate crop + text below.
    """
    x1, y1, x2, y2 = plate_bbox
    crop = _crop_bbox(frame, x1, y1, x2, y2, padding=4)

    # Upscale if too small
    ph, pw = crop.shape[:2]
    if pw < min_w:
        scale = min_w / max(pw, 1)
        crop = cv2.resize(
            crop, (int(pw * scale), int(ph * scale)),
            interpolation=cv2.INTER_CUBIC,
        )
        ph, pw = crop.shape[:2]

    # Yellow border
    bordered = cv2.copyMakeBorder(crop, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=_BBOX_COLOR_PLATE)
    ph_b, pw_b = bordered.shape[:2]

    # Text label below plate (plate_text on white bar)
    if plate_text:
        bar_h = 32
        bar = np.ones((bar_h, pw_b, 3), dtype=np.uint8) * 255  # white bar
        (tw, th), _ = cv2.getTextSize(plate_text, _LABEL_FONT, 0.85, 2)
        tx = max(4, (pw_b - tw) // 2)
        cv2.putText(bar, plate_text, (tx, bar_h - 8), _LABEL_FONT, 0.85, (30, 30, 30), 2, cv2.LINE_AA)
        result = np.vstack([bordered, bar])
    else:
        result = bordered

    return result


# ---------------------------------------------------------------------------
# ImageService
# ---------------------------------------------------------------------------

class ImageService:
    """
    Handles evidence image generation and upload to Supabase Storage.

    3 image types per violation:
      original  — raw full frame (no overlay) → legal evidence
      vehicle   — vehicle crop + red bbox draw + plate label
      plate     — plate crop enlarged + yellow border + text below
    """

    def __init__(self) -> None:
        self._storage = None
        self._bucket: str = "violations"
        self._quality: int = _DEFAULT_QUALITY
        self._max_w: int = _DEFAULT_MAX_W
        self._max_h: int = _DEFAULT_MAX_H
        self._plate_max_w: int = 320
        self._plate_max_h: int = 160
        self._vehicle_max_w: int = 640
        self._vehicle_max_h: int = 480
        self._storage_mode: str = "both"
        # 3 dedicated local folders — one per image type
        self._folder_original: Optional[Path] = None
        self._folder_vehicle: Optional[Path] = None
        self._folder_plate: Optional[Path] = None
        self._cloud_prefix: str = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self, supabase_client=None, local_settings=None) -> None:
        """Initialize storage and load WebP settings."""
        if supabase_client is not None:
            self._storage = supabase_client.storage
            logger.info("ImageService: Supabase Storage ready.")
        else:
            logger.warning("ImageService: No Supabase — local fallback only.")

        if local_settings is not None:
            self._quality = local_settings.get("violation", "image", "quality", default=80)
            self._max_w   = local_settings.get("violation", "image", "max_w", default=1280)
            self._max_h   = local_settings.get("violation", "image", "max_h", default=720)
            self._plate_max_w  = local_settings.get("violation", "image", "crop_plate_max_w", default=320)
            self._plate_max_h  = local_settings.get("violation", "image", "crop_plate_max_h", default=160)
            self._vehicle_max_w = local_settings.get("violation", "image", "crop_vehicle_max_w", default=640)
            self._vehicle_max_h = local_settings.get("violation", "image", "crop_vehicle_max_h", default=480)
            self._bucket   = local_settings.get("violation", "supabase_bucket", default="violations")
            self._storage_mode = local_settings.get("violation", "image_storage", default="both")

            # Load 3 per-type local folders
            folders = local_settings.get_section("violation", "local_folders")
            self._folder_original = Path(folders.get("original", "data/violations/original"))
            self._folder_vehicle  = Path(folders.get("vehicle",  "data/violations/vehicle"))
            self._folder_plate    = Path(folders.get("plate",    "data/violations/plate"))
        else:
            # Defaults if no local_settings
            self._folder_plate    = Path("data/violations/plate")

        # Derive cloud prefix from local_storage_path (e.g., "uploads/violations")
        # to match the folder structure shown in your Supabase screenshot.
        if local_settings:
            path_str = local_settings.get("violation", "local_storage_path", default="")
            self._cloud_prefix = path_str.strip("/") if path_str else ""
        else:
            self._cloud_prefix = "data/violations"

        # Create all 3 folders on disk
        for folder in (self._folder_original, self._folder_vehicle, self._folder_plate):
            folder.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"ImageService ready: quality={self._quality} "
            f"max={self._max_w}x{self._max_h} mode={self._storage_mode}\n"
            f"  original → {self._folder_original}\n"
            f"  vehicle  → {self._folder_vehicle}\n"
            f"  plate    → {self._folder_plate}"
        )

    # ------------------------------------------------------------------
    # Public: process all 3 evidence images in one call
    # ------------------------------------------------------------------

    def process_violation_images(
        self,
        frame: np.ndarray,
        vehicle_bbox: Optional[Tuple[int, int, int, int]] = None,
        plate_bbox:   Optional[Tuple[int, int, int, int]] = None,
        plate_text:   Optional[str] = None,
        confidence:   Optional[float] = None,
        camera_id:    int = 0,
        track_id:     int = 0,
    ) -> Dict:
        """
        Generate and upload 3 evidence images.

        Args:
            frame        : BGR numpy frame at moment of violation
            vehicle_bbox : (x1,y1,x2,y2) vehicle detection box
            plate_bbox   : (x1,y1,x2,y2) plate detection box
            plate_text   : Recognized plate string e.g. "MP04CF0655"
            confidence   : OCR/detection confidence 0-1
            camera_id    : For storage path organization
            track_id     : For unique filename

        Returns dict:
            {
              "original_url"  : str | None,  # Raw legal evidence
              "vehicle_url"   : str | None,  # Crop + red bbox drawn
              "plate_url"     : str | None,  # Plate crop + yellow border
              "full_image_url": str | None,  # Alias for original_url (DB compat)
              "cropped_vehicle_url": str | None,
              "cropped_plate_url"  : str | None,
            }
        """
        t0 = time.perf_counter()
        ts = int(time.time())
        uid = uuid.uuid4().hex[:8]
        base = f"cam{camera_id}/{ts}_{uid}_t{track_id}"

        result = {
            "original_url": None,
            "vehicle_url": None,
            "plate_url": None,
            # DB-compatible aliases
            "full_image_url": None,
            "cropped_vehicle_url": None,
            "cropped_plate_url": None,
        }

        # ── 1. ORIGINAL — full frame, NO overlay ──────────────────────
        original = _resize_if_needed(frame, self._max_w, self._max_h)
        orig_bytes = _encode_webp(original, self._quality)
        if orig_bytes:
            url = self._store(orig_bytes, f"{ts}_{uid}_t{track_id}.webp", image_type="original")
            result["original_url"] = url
            result["full_image_url"] = url   # DB alias

        # ── 2. VEHICLE — crop + draw bbox ────────────────────────────
        if vehicle_bbox is not None:
            x1, y1, x2, y2 = vehicle_bbox
            # Draw overlay on full frame first, then crop
            vis = draw_vehicle_evidence(
                frame,
                vehicle_bbox=vehicle_bbox,
                plate_text=plate_text,
                plate_bbox=plate_bbox,
                confidence=confidence,
            )
            crop_v = _crop_bbox(vis, x1, y1, x2, y2, padding=20)
            crop_v = _resize_if_needed(crop_v, self._vehicle_max_w, self._vehicle_max_h)
            veh_bytes = _encode_webp(crop_v, self._quality)
            if veh_bytes:
                url = self._store(veh_bytes, f"{ts}_{uid}_t{track_id}.webp", image_type="vehicle")
                result["vehicle_url"] = url
                result["cropped_vehicle_url"] = url

        # ── 3. PLATE — enlarged crop + yellow border + text ──────────
        if plate_bbox is not None:
            plate_img = draw_plate_crop(
                frame,
                plate_bbox=plate_bbox,
                plate_text=plate_text,
                min_w=200,
            )
            # Higher quality for OCR readability
            plate_bytes = _encode_webp(plate_img, min(95, self._quality + 10))
            if plate_bytes:
                url = self._store(plate_bytes, f"{ts}_{uid}_t{track_id}.webp", image_type="plate")
                result["plate_url"] = url
                result["cropped_plate_url"] = url

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(
            f"ImageService: cam{camera_id} track{track_id} "
            f"processed in {elapsed_ms:.1f}ms | "
            f"orig={self._kb(orig_bytes)} veh={self._kb(result['vehicle_url'])} "
            f"plate={self._kb(result['plate_url'])}"
        )
        return result

    def encode_frame_webp(
        self,
        frame: np.ndarray,
        max_w: Optional[int] = None,
        max_h: Optional[int] = None,
        quality: Optional[int] = None,
    ) -> Optional[bytes]:
        """Encode single frame to WebP bytes. Used for snapshot endpoint."""
        img = _resize_if_needed(frame, max_w or self._max_w, max_h or self._max_h)
        return _encode_webp(img, quality or self._quality)

    def upload_raw(self, data: bytes, path: str) -> Optional[str]:
        """Upload raw bytes to Supabase Storage."""
        return self._upload_to_supabase(data, path)

    # ------------------------------------------------------------------
    # Storage backend
    # ------------------------------------------------------------------

    def _store(
        self,
        data: bytes,
        filename: str,
        image_type: str = "original",
    ) -> Optional[str]:
        """
        Store image to local folder AND/OR Supabase Storage.

        image_type: "original" | "vehicle" | "plate"
          → routes to dedicated subfolder on disk
          → uses subfolder prefix in Supabase bucket path

        mode = "both"     → local + cloud simultaneously
        mode = "local"    → disk only
        mode = "supabase" → cloud only
        """
        # Map type → local folder
        folder_map = {
            "original": self._folder_original,
            "vehicle":  self._folder_vehicle,
            "plate":    self._folder_plate,
        }
        local_folder = folder_map.get(image_type, self._folder_original)

        # Supabase path includes type subfolder for organization
        # Prepend cloud_prefix if set (e.g., "uploads/violations/original/...")
        cloud_path = f"{image_type}/{filename}"
        if self._cloud_prefix:
            cloud_path = f"{self._cloud_prefix}/{cloud_path}"

        cloud_url = None
        local_path_result = None

        if self._storage_mode in ("supabase", "both") and self._storage is not None:
            cloud_url = self._upload_to_supabase(data, cloud_path)

        if self._storage_mode in ("local", "both") and local_folder is not None:
            local_path_result = self._save_local(data, filename, local_folder)

        # Return cloud URL if available, else local URL
        if cloud_url:
            return cloud_url
        if local_path_result:
            return f"/violations/images/{image_type}/{filename}"
        return None

    def _upload_to_supabase(self, data: bytes, path: str) -> Optional[str]:
        """Upload to Supabase Storage, return public URL."""
        if self._storage is None:
            return None
        try:
            self._storage.from_(self._bucket).upload(
                path=path,
                file=data,
                file_options={"content-type": "image/webp", "upsert": "true"},
            )
            url = self._storage.from_(self._bucket).get_public_url(path)
            return url if isinstance(url, str) else None
        except Exception as e:
            logger.error(f"Supabase upload failed ({path}): {e}")
            return None

    def _save_local(self, data: bytes, filename: str, folder: Path) -> Optional[Path]:
        """Save bytes to a specific folder (original / vehicle / plate)."""
        try:
            dest = folder / filename
            dest.write_bytes(data)
            return dest
        except Exception as e:
            logger.error(f"Local save failed ({folder / filename}): {e}")
            return None

    @staticmethod
    def _kb(obj) -> str:
        if isinstance(obj, bytes):
            return f"{len(obj)/1024:.1f}KB"
        return "–"
