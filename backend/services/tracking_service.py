"""
tracking_service.py — SORT Tracker: theo dõi nhiều phương tiện qua các frame
Thuật toán: Kalman Filter dự đoán vị trí + Hungarian Algorithm ghép detection
"""
import numpy as np
from scipy.optimize import linear_sum_assignment


class KalmanFilter:
    """Bộ lọc Kalman đơn giản cho bounding box — trạng thái [x, y, w, h, vx, vy]"""

    def __init__(self, bbox):
        x1, y1, x2, y2 = bbox
        self.x = np.array([x1, y1, x2 - x1, y2 - y1, 0.0, 0.0], dtype=float)
        self.P = np.eye(6) * 10       # Ma trận hiệp phương sai
        self.F = np.eye(6)            # Ma trận chuyển trạng thái
        self.F[0, 4] = 1              # x += vx
        self.F[1, 5] = 1              # y += vy
        self.Q = np.eye(6) * 0.1     # Nhiễu quá trình
        self.R = np.eye(4) * 1.0     # Nhiễu đo lường
        self.H = np.zeros((4, 6))    # Ma trận đo lường (chỉ lấy x,y,w,h)
        self.H[0, 0] = self.H[1, 1] = self.H[2, 2] = self.H[3, 3] = 1

    def predict(self):
        """Dự đoán trạng thái tiếp theo"""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.get_bbox()

    def update(self, bbox):
        """Cập nhật với observation mới"""
        x1, y1, x2, y2 = bbox
        z = np.array([x1, y1, x2 - x1, y2 - y1])
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(6) - K @ self.H) @ self.P

    def get_bbox(self):
        """Trả về [x1, y1, x2, y2]"""
        x, y, w, h = self.x[0], self.x[1], self.x[2], self.x[3]
        return [x, y, x + w, y + h]


class Track:
    """Track đơn lẻ của một phương tiện"""
    _id_counter = 1

    def __init__(self, bbox, detection_data):
        self.id = Track._id_counter
        Track._id_counter += 1
        self.kf = KalmanFilter(bbox)
        self.age = 0
        self.hits = 1
        self.hit_streak = 1
        self.time_since_update = 0
        self.detections = [detection_data]

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
    """
    SORT Tracker — theo dõi nhiều phương tiện qua các frame ảnh.

    Tham số:
        max_age: Số frame tối đa không khớp trước khi xóa track
        min_hits: Số frame tối thiểu để track được công nhận (tránh false positive)
        iou_threshold: Ngưỡng IoU để ghép detection↔track
    """

    def __init__(self, max_age: int = 3, min_hits: int = 2, iou_threshold: float = 0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.tracks: list = []
        self.frame_count = 0

    def update(self, detections: list) -> list:
        """
        Cập nhật tracker với danh sách detection mới.

        Input:  List[{"bbox": {"x1","y1","x2","y2"}, "plate_text": str, "confidence": float}]
        Output: List[{"track_id", "bbox", "detections", "hits"}] — chỉ track đủ min_hits
        """
        self.frame_count += 1

        # Dự đoán vị trí tiếp theo của tất cả track
        for track in self.tracks:
            track.predict()

        # Ghép detection vào track hiện có (nếu có cả hai)
        if detections and self.tracks:
            matched, unmatched_dets, _ = self._match(detections)

            for det_idx, trk_idx in matched:
                bbox = self._bbox_to_list(detections[det_idx]["bbox"])
                self.tracks[trk_idx].update(bbox, detections[det_idx])

            for det_idx in unmatched_dets:
                bbox = self._bbox_to_list(detections[det_idx]["bbox"])
                self.tracks.append(Track(bbox, detections[det_idx]))

            # Xóa track bị bỏ quá lâu
            self.tracks = [t for t in self.tracks if t.time_since_update < self.max_age]

        elif detections:
            # Không có track nào — tạo mới tất cả
            for det in detections:
                self.tracks.append(Track(self._bbox_to_list(det["bbox"]), det))

        # Trả về danh sách track hợp lệ (đủ số lần xuất hiện)
        return [
            {
                "track_id": t.id,
                "bbox": self._list_to_bbox(t.get_state()),
                "detections": t.detections,
                "hits": t.hits,
            }
            for t in self.tracks
            if t.hit_streak >= self.min_hits
        ]

    def _match(self, detections: list):
        """Ghép detections với tracks bằng IoU + Hungarian Algorithm"""
        iou_mat = np.zeros((len(detections), len(self.tracks)))
        for d, det in enumerate(detections):
            det_box = self._bbox_to_list(det["bbox"])
            for t, trk in enumerate(self.tracks):
                iou_mat[d, t] = self._iou(det_box, trk.get_state())

        if min(iou_mat.shape) > 0:
            rows, cols = linear_sum_assignment(-iou_mat)
            pairs = list(zip(rows.tolist(), cols.tolist()))
        else:
            pairs = []

        matched_det = set()
        matched_trk = set()
        matches = []
        for d, t in pairs:
            if iou_mat[d, t] >= self.iou_threshold:
                matches.append((d, t))
                matched_det.add(d)
                matched_trk.add(t)

        unmatched_dets = [d for d in range(len(detections)) if d not in matched_det]
        unmatched_trks = [t for t in range(len(self.tracks)) if t not in matched_trk]
        return matches, unmatched_dets, unmatched_trks

    @staticmethod
    def _iou(b1: list, b2: list) -> float:
        """Tính IoU (Intersection over Union) giữa hai bounding box"""
        xi1 = max(b1[0], b2[0]); yi1 = max(b1[1], b2[1])
        xi2 = min(b1[2], b2[2]); yi2 = min(b1[3], b2[3])
        inter = max(0.0, xi2 - xi1) * max(0.0, yi2 - yi1)
        area1 = max(0.0, b1[2] - b1[0]) * max(0.0, b1[3] - b1[1])
        area2 = max(0.0, b2[2] - b2[0]) * max(0.0, b2[3] - b2[1])
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _bbox_to_list(bbox_dict: dict) -> list:
        return [bbox_dict["x1"], bbox_dict["y1"], bbox_dict["x2"], bbox_dict["y2"]]

    @staticmethod
    def _list_to_bbox(bbox_list: list) -> dict:
        return {
            "x1": int(bbox_list[0]), "y1": int(bbox_list[1]),
            "x2": int(bbox_list[2]), "y2": int(bbox_list[3]),
        }
