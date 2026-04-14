"""
ViolationProcessor — Background task xử lý I/O nặng.

Consume ViolationEvent từ queue → render 3 ảnh WebP → upload Supabase → DB insert.
Tách hoàn toàn khỏi AI loop để stream_worker không bị block.

Flow mới (clean):
    ViolationEngine  →  asyncio.Queue  →  ViolationProcessor
    (enqueue nhẹ)       (buffer)          (render ảnh + upload + lưu DB)

Dùng:
  - api/services/ImageService  → render 3 ảnh WebP (original/vehicle/plate) + upload Supabase
  - api/services/DBService     → insert violations table
"""
from __future__ import annotations

import asyncio
from datetime import timezone
from typing import Optional

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class ViolationProcessor:
    """Consume ViolationEvent queue và xử lý toàn bộ I/O nặng trong background."""

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue   = queue
        self._running = False
        # Callback inject từ DetectionWorker để bridge về Qt (thay SSE)
        # Signature: (violation_dict) -> None
        self._on_saved = None

        # Lazy-init services (tránh import lúc module load)
        self._img_svc = None
        self._db_svc  = None

    def _ensure_services(self) -> None:
        """Lazy-load API services (ImageService & DBService)."""
        if self._img_svc:
            return

        try:
            # Use absolute import from project root
            from backend.api.dependencies import image_service, db_service
            self._img_svc = image_service
            self._db_svc  = db_service
            logger.info("⚙️  [PROCESSOR] API services connected")
        except ImportError as e:
            logger.error(f"❌ [PROCESSOR] Import error: {e}")

    async def run_loop(self) -> None:
        """Chạy vĩnh viễn trong background task — xử lý queue vi phạm."""
        self._running = True
        self._ensure_services()
        logger.info("⚙️  [PROCESSOR] Background loop started")

        while self._running:
            try:
                from backend.services.violation_engine import ViolationEvent
                event: ViolationEvent = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                try:
                    await self._process(event)
                except Exception as exc:
                    logger.error(
                        "❌ [Processor] Lỗi xử lý | cam=%s track=%s: %s",
                        event.camera_id, event.track_id, exc,
                    )
                finally:
                    self._queue.task_done()

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                import traceback
                logger.error("❌ [Processor] Loop lỗi:\n%s", traceback.format_exc())

        logger.info("⏹️  [Processor] Đã dừng")

    async def stop(self) -> None:
        self._running = False

    # ──────────────────────────── Core Processing ────────────────────────────

    async def _process(self, event) -> None:
        """Toàn bộ I/O nặng cho 1 vi phạm: render 3 ảnh → upload → DB."""
        plate_text = event.plate_text or "N/A"
        plate_conf = event.plate_conf or 0.0

        # ── Render 3 ảnh WebP + upload Supabase ──────────────────────────
        urls = await self._render_and_upload(event, plate_text, plate_conf)

        # ── Lưu vào DB ──────────────────────────────────────────────────
        if self._db_svc is None or not self._db_svc.is_connected:
            logger.error("❌ [Processor] DB chưa connected | cam=%s", event.camera_id)
            return

        violation_ts = (event.crossing_ts or event.timestamp)
        if violation_ts.tzinfo is not None:
            violation_ts = violation_ts.astimezone(timezone.utc)

        violation_data = {
            "camera_id": event.camera_id,
            "timestamp": violation_ts.isoformat(),
            "violation_type": "red_light",
            "traffic_light_state": "red",
            "license_plate": plate_text if plate_text != "N/A" else None,
            "confidence": round(plate_conf, 4) if plate_conf > 0 else None,
            "track_id": event.track_id,
            "full_image_url": urls.get("full_image_url") or "",
            "cropped_vehicle_url": urls.get("cropped_vehicle_url"),
            "cropped_plate_url": urls.get("cropped_plate_url"),
        }
        # Thêm bbox xe nếu có
        if event.track_bbox:
            x1, y1, x2, y2 = event.track_bbox
            violation_data.update({
                "bbox_x": x1, "bbox_y": y1,
                "bbox_w": x2 - x1, "bbox_h": y2 - y1,
            })

        # Filter None values
        violation_data = {k: v for k, v in violation_data.items() if v is not None}

        try:
            result = await asyncio.to_thread(self._db_svc.create_violation, violation_data)
        except Exception as exc:
            logger.error(
                "❌ [Processor] DB lỗi | cam=%s track=%s: %s",
                event.camera_id, event.track_id, exc,
            )
            return

        if result:
            violation_label = getattr(event, "violation_label", "RED")
            logger.warning(
                "🚨 [PROCESSOR] Lưu DB thành công | cam=%s | biển=%s (%.0f%%) | track=%s | label=%s | id=%s",
                event.camera_id,
                plate_text, plate_conf * 100,
                event.track_id,
                violation_label,
                result.get("id", "?"),
            )
            # Bridge về PyQt5 UI
            if self._on_saved and isinstance(result, dict):
                try:
                    self._on_saved(result)
                except Exception as cb_exc:
                    logger.warning("[Processor] on_saved callback lỗi: %s", cb_exc)
        else:
            logger.warning(
                "⚠️ [PROCESSOR] DB insert thất bại | cam=%s | track=%s",
                event.camera_id, event.track_id,
            )

    async def _render_and_upload(self, event, plate_text: str, plate_conf: float) -> dict:
        """Render 3 ảnh WebP qua api/services/ImageService + upload Supabase.

        3 ảnh:
          original  — Full frame, KHÔNG overlay (bằng chứng pháp lý)
          vehicle   — Crop xe + khung đỏ + biển số label
          plate     — Biển số phóng to + viền vàng + text
        """
        if self._img_svc is None:
            logger.warning("⚠️ [Processor] ImageService chưa init")
            return {}

        try:
            urls = await asyncio.to_thread(
                self._img_svc.process_violation_images,
                frame=event.best_frame,
                vehicle_bbox=event.track_bbox,
                plate_bbox=event.plate_bbox,
                plate_text=plate_text if plate_text != "N/A" else None,
                confidence=plate_conf if plate_conf > 0 else None,
                camera_id=event.camera_id,
                track_id=event.track_id,
            )
            return urls or {}
        except Exception as exc:
            logger.warning(
                "⚠️ [Processor] Render/Upload lỗi | cam=%s track=%s: %s",
                event.camera_id, event.track_id, exc,
            )
            return {}
