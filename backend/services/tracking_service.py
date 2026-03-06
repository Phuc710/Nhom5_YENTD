"""
SORT Tracker - Simple Online Realtime Tracking
Track multiple vehicles across frames
"""
import numpy as np
from scipy.optimize import linear_sum_assignment

class KalmanFilter:
    """Simple Kalman filter for bounding box tracking"""
    def __init__(self, bbox):
        # State: [x, y, w, h, vx, vy]
        self.x = np.array([bbox[0], bbox[1], bbox[2]-bbox[0], bbox[3]-bbox[1], 0, 0], dtype=float)
        self.P = np.eye(6) * 10  # Covariance
        self.F = np.eye(6)  # State transition
        self.F[0, 4] = 1
        self.F[1, 5] = 1
        self.Q = np.eye(6) * 0.1  # Process noise
        self.R = np.eye(4) * 1  # Measurement noise
        self.H = np.zeros((4, 6))  # Measurement matrix
        self.H[0, 0] = 1
        self.H[1, 1] = 1
        self.H[2, 2] = 1
        self.H[3, 3] = 1
    
    def predict(self):
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.get_bbox()
    
    def update(self, bbox):
        z = np.array([bbox[0], bbox[1], bbox[2]-bbox[0], bbox[3]-bbox[1]])
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(6) - K @ self.H) @ self.P
    
    def get_bbox(self):
        x, y, w, h = self.x[0], self.x[1], self.x[2], self.x[3]
        return [x, y, x+w, y+h]

class Track:
    """Single vehicle track"""
    _id_counter = 1
    
    def __init__(self, bbox, detection_data):
        self.id = Track._id_counter
        Track._id_counter += 1
        self.kf = KalmanFilter(bbox)
        self.age = 0
        self.hits = 1
        self.hit_streak = 1
        self.time_since_update = 0
        self.detections = [detection_data]  # Store OCR results
    
    def predict(self):
        self.age += 1
        self.time_since_update += 1
        return self.kf.predict()
    
    def update(self, bbox, detection_data):
        self.kf.update(bbox)
        self.hits += 1
        self.hit_streak += 1
        self.time_since_update = 0
        self.detections.append(detection_data)
    
    def get_state(self):
        return self.kf.get_bbox()

class SORTTracker:
    """SORT tracker for multiple vehicles"""
    def __init__(self, max_age=3, min_hits=2, iou_threshold=0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.tracks = []
        self.frame_count = 0
    
    def update(self, detections):
        """
        Update tracker with new detections
        
        Args:
            detections: List of {
                "bbox": {"x1": int, "y1": int, "x2": int, "y2": int},
                "plate_text": str,
                "confidence": float
            }
        
        Returns:
            List of active tracks with track_id
        """
        self.frame_count += 1
        
        # Predict existing tracks
        for track in self.tracks:
            track.predict()
        
        # Match detections to tracks
        if len(detections) > 0 and len(self.tracks) > 0:
            matched, unmatched_dets, unmatched_trks = self._match(detections)
            
            # Update matched tracks
            for det_idx, trk_idx in matched:
                bbox = self._bbox_dict_to_array(detections[det_idx]["bbox"])
                self.tracks[trk_idx].update(bbox, detections[det_idx])
            
            # Create new tracks for unmatched detections
            for det_idx in unmatched_dets:
                bbox = self._bbox_dict_to_array(detections[det_idx]["bbox"])
                self.tracks.append(Track(bbox, detections[det_idx]))
            
            # Remove dead tracks
            self.tracks = [t for t in self.tracks if t.time_since_update < self.max_age]
        
        elif len(detections) > 0:
            # No existing tracks, create new ones
            for det in detections:
                bbox = self._bbox_dict_to_array(det["bbox"])
                self.tracks.append(Track(bbox, det))
        
        # Return active tracks (min_hits requirement)
        active_tracks = []
        for track in self.tracks:
            if track.hit_streak >= self.min_hits:
                active_tracks.append({
                    "track_id": track.id,
                    "bbox": self._bbox_array_to_dict(track.get_state()),
                    "detections": track.detections,
                    "hits": track.hits
                })
        
        return active_tracks
    
    def _match(self, detections):
        """Match detections to tracks using IoU"""
        iou_matrix = np.zeros((len(detections), len(self.tracks)))
        
        for d, det in enumerate(detections):
            det_bbox = self._bbox_dict_to_array(det["bbox"])
            for t, trk in enumerate(self.tracks):
                trk_bbox = trk.get_state()
                iou_matrix[d, t] = self._iou(det_bbox, trk_bbox)
        
        # Hungarian algorithm for optimal matching
        if min(iou_matrix.shape) > 0:
            matched_indices = linear_sum_assignment(-iou_matrix)
            matched_indices = np.array(list(zip(*matched_indices)))
        else:
            matched_indices = np.empty((0, 2), dtype=int)
        
        # Filter matches by IoU threshold
        matches = []
        unmatched_detections = []
        unmatched_tracks = []
        
        for d, det in enumerate(detections):
            if d not in matched_indices[:, 0]:
                unmatched_detections.append(d)
        
        for t, trk in enumerate(self.tracks):
            if t not in matched_indices[:, 1]:
                unmatched_tracks.append(t)
        
        for d, t in matched_indices:
            if iou_matrix[d, t] < self.iou_threshold:
                unmatched_detections.append(d)
                unmatched_tracks.append(t)
            else:
                matches.append((d, t))
        
        return matches, unmatched_detections, unmatched_tracks
    
    def _iou(self, bbox1, bbox2):
        """Calculate IoU between two bboxes"""
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])
        
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0
    
    def _bbox_dict_to_array(self, bbox_dict):
        return [bbox_dict["x1"], bbox_dict["y1"], bbox_dict["x2"], bbox_dict["y2"]]
    
    def _bbox_array_to_dict(self, bbox_array):
        return {
            "x1": int(bbox_array[0]),
            "y1": int(bbox_array[1]),
            "x2": int(bbox_array[2]),
            "y2": int(bbox_array[3])
        }
