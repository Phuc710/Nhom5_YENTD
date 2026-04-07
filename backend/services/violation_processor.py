"""
ViolationProcessor — Background task xử lý I/O nặng sau khi ViolationEngine xác nhận vi phạm.

Vai trò duy nhất: consume ViolationEvent từ queue → OCR voting → upload ảnh → DB insert → SSE push.
Tách hoàn toàn khỏi AI loop để stream_worker không bị block.

Flow:
    ViolationEngine  →  asyncio.Queue  →  ViolationProcessor
    (enqueue nhẹ)       (buffer)          (OCR + upload + lưu DB)
"""
from __future__ import annotations

import asyncio
from datetime import timezone
from typing import Optional, Tuple

from backend.database.models import TrafficLightState
from backend.services.image_service import ImageService
from backend.services.violation_service import ViolationService
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class ViolationProcessor:
    """Consume ViolationEvent queue và xử lý toàn bộ I/O nặng trong background."""

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue   = queue
        self._vio_svc = ViolationService()
        self._img_svc = ImageService()
        self._running = False
        # Callback inject từ DetectionWorker để bridge về Qt (thay SSE)
        # Signature: (violation_dict) -> None
        self._on_saved = None

    async def run_loop(self) -> None:
        """Chạy vĩnh viễn trong background task — gọi từ StreamWorker."""
        self._running = True
        logger.info("⚙️  [PROCESSOR] Khởi động violation processor thành công")

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
        """Toàn bộ I/O nặng cho 1 vi phạm: OCR vote → crop + upload → DB → SSE."""
        plate_text, plate_conf = _vote_plate(event.ocr_votes)

        # Upload ảnh bằng chứng song song
        vehicle_url, plate_url, snapshot_url = await self._upload_evidence(event)

        # Lưu vào DB
        try:
            result = await self._vio_svc.create_violation(
                camera_id              = event.camera_id,
                image_url              = snapshot_url or "",
                plate_image_url        = plate_url,
                cropped_vehicle_url    = vehicle_url,
                stop_line_snapshot_url = snapshot_url,
                license_plate          = plate_text,
                confidence             = round(plate_conf, 4),
                traffic_light_state    = TrafficLightState.RED,
                timestamp              = (event.crossing_ts or event.timestamp).astimezone(timezone.utc),
                vote_count             = len(event.ocr_votes),
                vote_percent           = round(plate_conf * 100, 2),
                total_frames           = event.track_age,
                track_id               = event.track_id,
            )
        except Exception as exc:
            logger.error(
                "❌ [Processor] DB lỗi | cam=%s track=%s: %s",
                event.camera_id, event.track_id, exc,
            )
            return

        if isinstance(result, dict) and result.get("success") is not False:
            logger.info(
                "🚨 [VIOLATION] XÁC NHẬN | cam=%s | biển=%s (%.0f%%) | track=%s | ảnh=%s",
                event.camera_id,
                plate_text or "N/A", plate_conf * 100,
                event.track_id,
                "✅ OK" if snapshot_url else "❌ Lỗi",
            )
            # Bridge về PyQt5 UI thay vì SSE
            if self._on_saved and isinstance(result, dict):
                try:
                    self._on_saved(result)
                except Exception as cb_exc:
                    logger.warning("[Processor] on_saved callback lỗi: %s", cb_exc)
        else:
            logger.debug(
                "📋 [PROCESSOR] Bỏ qua (đã tồn tại) | cam=%s | track=%s",
                event.camera_id, event.track_id
            )

    async def _upload_evidence(self, event) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Crop + upload ảnh song song để tiết kiệm thời gian."""
        import numpy as np

        try:
            frame = event.best_frame
            h, w  = frame.shape[:2]
            x1, y1, x2, y2 = event.track_bbox

            # Vehicle crop — padding rộng để có context
            pad_x = max(40, (x2 - x1) * 2)
            pad_y = max(30, (y2 - y1) * 3)
            vehicle_crop = frame[
                max(0, y1 - int(pad_y)) : min(h, y2 + int(pad_y // 2)),
                max(0, x1 - int(pad_x)) : min(w, x2 + int(pad_x)),
            ]

            # Plate crop — bbox trực tiếp
            plate_crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]

            # Upload 3 ảnh song song
            vehicle_url, plate_url, snapshot_url = await asyncio.gather(
                self._img_svc.save_vehicle_image(vehicle_crop, event.camera_id),
                self._img_svc.save_plate_image(plate_crop, event.camera_id),
                self._img_svc.save_full_image(event.crossing_frame, event.camera_id),
                return_exceptions=True,
            )

            # Xử lý nếu có exception trong gather
            return (
                vehicle_url  if not isinstance(vehicle_url, Exception) else None,
                plate_url    if not isinstance(plate_url, Exception)   else None,
                snapshot_url if not isinstance(snapshot_url, Exception) else None,
            )

        except Exception as exc:
            logger.warning(
                "⚠️ [Processor] Upload lỗi | cam=%s track=%s: %s",
                event.camera_id, event.track_id, exc,
            )
            return None, None, None


# ─────────────────────────────── Utilities ───────────────────────────────────

def _vote_plate(votes) -> Tuple[Optional[str], float]:
    """Voting OCR: chọn plate text xuất hiện nhiều nhất với confidence cao nhất."""
    if not votes:
        return None, 0.0
    counts: dict = {}
    for text, conf in votes:
        if text:
            counts.setdefault(text, []).append(conf)
    if not counts:
        return None, 0.0
    best = max(counts, key=lambda t: (len(counts[t]), sum(counts[t]) / len(counts[t])))
    avg  = sum(counts[best]) / len(counts[best])
    return best, avg
