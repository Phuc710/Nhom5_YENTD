import cv2
import numpy as np
from typing import Dict, List, Any, Optional

from backend.ml.detector import get_detector
from backend.services.plate_tracker import PlateTracker, TrackState

class VehicleState:
    """Mock vehicle state to satisfy ALPRService expectations."""
    def __init__(self, track: TrackState):
        self.bbox_xyxy = track.bbox
        self.vehicle_type = "vehicle"  # Default
        self.plate_number = track.best_plate_text if track.best_plate_text else ""
        self.ocr_conf = track.best_plate_conf
        self.license_plate_bbox = track.plate_bbox

class ALPRCore:
    """
    Unified ALPR core that combines detection and tracking.
    Restores compatibility with ALPRService.
    """
    def __init__(self, opts: Any):
        self.opts = opts
        self.detector = get_detector()
        
        # Initialize tracker
        mode = "deepsort" if getattr(opts, "deepsort", False) else "iou"
        self._tracker = PlateTracker(
            mode=mode,
            model_path=getattr(opts, "dsort_weight", "models/deepsort/ckpt.t7")
        )
        
        # Sync attributes expected by ALPRService
        self.ocr_thres = getattr(opts, "ocr_thres", 0.9)
        self.read_plate = getattr(opts, "read_plate", True)
        self.deepsort = getattr(opts, "deepsort", False)
        self.lang = getattr(opts, "lang", "en")

    def reset(self):
        """Reset tracker state."""
        self._tracker.reset()

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Process a single frame: Detect -> Track -> Annotate.
        Returns: annotated_frame
        """
        if frame is None:
            return frame

        # 1. Detection
        detections = self.detector.process_frame(
            frame, 
            ocr_enabled=self.read_plate
        )

        # 2. Tracking
        active_tracks = self._tracker.update(detections, frame=frame)

        # 3. Annotation (Basic)
        annotated = frame.copy()
        for track in active_tracks:
            x1, y1, x2, y2 = track.bbox
            # Draw vehicle/plate box
            cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            
            # Draw label
            label = f"ID:{track.track_id}"
            if track.best_plate_text:
                label += f" | {track.best_plate_text}"
            
            cv2.putText(
                annotated, label, (int(x1), int(y1) - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2
            )

        return annotated

    @property
    def vehicles(self) -> Dict[int, VehicleState]:
        """Expose tracks as vehicle objects for ALPRService."""
        tracks = self._tracker.get_active_tracks()
        return {t.track_id: VehicleState(t) for t in tracks}
