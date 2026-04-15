import logging
import math
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import cv2
from ultralytics import YOLO

import configs.settings as cfg


def setup_logging(log_dir=cfg.LOG_DIR, log_level=cfg.LOG_LEVEL):
    """
    Thiet lap logging vua ghi ra console, vua ghi ra file.

    Ly do nen co logging trong mot du an nghiem tuc:
    - Khi demo bi loi, log cho ta biet chuong trinh dang dung o buoc nao.
    - Khi chay nhieu video, log giup doi chieu ket qua va truy vet su co.
    - Day la thoi quen rat giong voi cac he thong production.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / f"vehicle_counter_{datetime.now():%Y%m%d_%H%M%S}.log"
    logger = logging.getLogger("vehicle_counter")
    logger.setLevel(getattr(logging, str(log_level).upper(), logging.INFO))
    logger.propagate = False

    # Neu goi lai setup_logging trong cung mot process thi xoa handler cu
    # de tranh bi in lap log nhieu lan.
    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    logger.info("Log file duoc tao tai: %s", log_path)
    return logger


class VehicleCounterPro:
    """
    He thong dem xe theo phong cach huong doi tuong.

    Nhiem vu chinh cua lop nay:
    1. Nap model YOLO.
    2. Dung tracker de gan ID on dinh cho tung xe.
    3. Theo doi tam diem cua moi xe qua tung frame.
    4. Dem xe khi tam diem di cat qua vach dem.
    5. Ve UI chuyen nghiep de quan sat ket qua.
    """

    def __init__(self, model_path, confidence=cfg.CONFIDENCE_THRESHOLD, tracker=cfg.TRACKER_TYPE):
        cfg.ensure_project_dirs()

        self.logger = logging.getLogger("vehicle_counter")
        self.logger.info("Dang khoi tao mo hinh YOLO tu: %s", model_path)

        self.model = YOLO(str(model_path))
        self.confidence = confidence
        self.tracker = tracker

        # Chuyen tu ten class sang ID class theo model dang su dung.
        # Cach nay de doc hon viec hard-code ID trong source code.
        self.target_class_ids = [
            class_id
            for class_id, class_name in self.model.names.items()
            if class_name in cfg.TARGET_CLASS_NAMES
        ]

        self.total_count = 0
        self.counted_ids = set()
        self.track_history = {}
        self.track_trace = defaultdict(list)
        self.frame_index = 0
        self.current_fps = 0.0
        self._fps_timer = time.perf_counter()

        self.logger.info("Class dang dem: %s", ", ".join(cfg.TARGET_CLASS_NAMES))
        self.logger.info("Tracker dang dung: %s", self.tracker)

    def resize_frame(self, frame):
        """
        Doi kich thuoc khung hinh de giao dien de quan sat hon.
        Neu cau hinh de None thi ta giu nguyen video goc.
        """
        if cfg.DISPLAY_WIDTH is None or cfg.DISPLAY_HEIGHT is None:
            return frame
        return cv2.resize(frame, (cfg.DISPLAY_WIDTH, cfg.DISPLAY_HEIGHT))

    @staticmethod
    def get_box_center(box):
        """
        Lay tam diem bounding box.
        Tam diem duoc dung lam dai dien cho vi tri chuyen dong cua xe.
        """
        x1, y1, x2, y2 = box
        return int((x1 + x2) / 2), int((y1 + y2) / 2)

    @staticmethod
    def point_line_distance(point, line_start, line_end):
        """
        Tinh khoang cach tu 1 diem den doan thang vach dem.

        Ham nay giup ta xac nhan xe dang thuc su di gan vach,
        tranh truong hop ve mat hinh hoc xe cat duong keo dai nhung thuc te
        lai o xa khu vuc dem.
        """
        px, py = point
        x1, y1 = line_start
        x2, y2 = line_end

        line_dx = x2 - x1
        line_dy = y2 - y1

        if line_dx == 0 and line_dy == 0:
            return math.hypot(px - x1, py - y1)

        projection = ((px - x1) * line_dx + (py - y1) * line_dy) / float(
            line_dx * line_dx + line_dy * line_dy
        )
        projection = max(0.0, min(1.0, projection))

        nearest_x = x1 + projection * line_dx
        nearest_y = y1 + projection * line_dy
        return math.hypot(px - nearest_x, py - nearest_y)

    @staticmethod
    def ccw(point_a, point_b, point_c):
        """
        Ham hinh hoc co ban de xac dinh huong quay cua 3 diem.
        Day la thanh phan ho tro phep kiem tra cat nhau cua 2 doan thang.
        """
        return (point_c[1] - point_a[1]) * (point_b[0] - point_a[0]) > (
            point_b[1] - point_a[1]
        ) * (point_c[0] - point_a[0])

    def segments_intersect(self, point_a, point_b, point_c, point_d):
        """
        Kiem tra doan AB co cat doan CD hay khong.

        Trong bai toan nay:
        - AB: duong di cua tam xe tu frame truoc sang frame hien tai
        - CD: vach dem

        Neu 2 doan cat nhau, kha nang cao la xe vua di qua vach.
        """
        return (self.ccw(point_a, point_c, point_d) != self.ccw(point_b, point_c, point_d)) and (
            self.ccw(point_a, point_b, point_c) != self.ccw(point_a, point_b, point_d)
        )

    def has_crossed_counting_line(self, previous_center, current_center):
        """
        Logic dem xe cot loi.

        Ta khong dem dua vao so luong ID xuat hien trong toan video,
        vi cach do de dem nham khi tracker mat roi bat lai doi tuong.

        Thay vao do:
        1. Lay tam xe cua frame truoc va frame hien tai.
        2. Noi 2 tam diem thanh mot doan ngan.
        3. Neu doan nay cat vach dem thi xe da di qua vach.
        4. Moi ID chi duoc dem 1 lan duy nhat.
        """
        line_start = cfg.COUNT_LINE_START
        line_end = cfg.COUNT_LINE_END

        is_intersected = self.segments_intersect(
            previous_center, current_center, line_start, line_end
        )
        if not is_intersected:
            return False

        current_distance = self.point_line_distance(current_center, line_start, line_end)
        previous_distance = self.point_line_distance(previous_center, line_start, line_end)

        return (
            current_distance <= cfg.LINE_CROSS_MARGIN * 2
            or previous_distance <= cfg.LINE_CROSS_MARGIN * 2
        )

    def get_vehicle_color(self, class_name):
        """
        Chon mau khac nhau theo loai xe de khung hinh trong va de theo doi hon.
        """
        return cfg.COLORS.get(class_name, cfg.COLORS["fallback"])

    @staticmethod
    def draw_transparent_panel(frame, top_left, bottom_right, color, alpha):
        """
        Ve nen mo de text van ro tren nhieu nen video khac nhau.
        """
        overlay = frame.copy()
        cv2.rectangle(overlay, top_left, bottom_right, color, -1)
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    def draw_glass_panel(self, frame, top_left, bottom_right, alpha=None):
        """
        Ve panel theo phong cach HUD:
        - Nen toi trong mo
        - Vien xanh cyan
        - Co duong highlight phia tren de tao cam giac "glass"
        """
        if alpha is None:
            alpha = cfg.PANEL_ALPHA

        self.draw_transparent_panel(frame, top_left, bottom_right, cfg.COLORS["panel"], alpha)
        cv2.rectangle(
            frame,
            top_left,
            bottom_right,
            cfg.COLORS["panel_border"],
            2,
            cv2.LINE_AA,
        )

        x1, y1 = top_left
        x2, y2 = bottom_right
        highlight_bottom = min(y1 + 18, y2)
        self.draw_transparent_panel(
            frame,
            (x1 + 1, y1 + 1),
            (x2 - 1, highlight_bottom),
            cfg.COLORS["panel_soft"],
            0.28,
        )

    @staticmethod
    def draw_corner_box(frame, box, color, thickness=2, radius=12):
        """
        Ve bounding box phong cach goc bo tron.
        Cach ve nay trong gon va hien dai hon box chu nhat co ban.
        """
        x1, y1, x2, y2 = box
        radius = min(radius, abs(x2 - x1) // 4, abs(y2 - y1) // 4)

        if radius <= 0:
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
            return

        cv2.line(frame, (x1 + radius, y1), (x2 - radius, y1), color, thickness)
        cv2.line(frame, (x1 + radius, y2), (x2 - radius, y2), color, thickness)
        cv2.line(frame, (x1, y1 + radius), (x1, y2 - radius), color, thickness)
        cv2.line(frame, (x2, y1 + radius), (x2, y2 - radius), color, thickness)

        cv2.ellipse(frame, (x1 + radius, y1 + radius), (radius, radius), 180, 0, 90, color, thickness)
        cv2.ellipse(frame, (x2 - radius, y1 + radius), (radius, radius), 270, 0, 90, color, thickness)
        cv2.ellipse(frame, (x1 + radius, y2 - radius), (radius, radius), 90, 0, 90, color, thickness)
        cv2.ellipse(frame, (x2 - radius, y2 - radius), (radius, radius), 0, 0, 90, color, thickness)

    def draw_neon_box(self, frame, box, color):
        """
        Ve box theo 2 lop:
        1. Lop glow o ngoai de tao hieu ung neon
        2. Lop corner box chinh de giu duoc do sac net
        """
        x1, y1, x2, y2 = box
        glow_overlay = frame.copy()

        for expand in cfg.NEON_GLOW_STEPS:
            alpha = 0.05 if expand >= 12 else 0.08
            cv2.rectangle(
                glow_overlay,
                (max(0, x1 - expand), max(0, y1 - expand)),
                (min(frame.shape[1] - 1, x2 + expand), min(frame.shape[0] - 1, y2 + expand)),
                color,
                2,
                cv2.LINE_AA,
            )
            cv2.addWeighted(glow_overlay, alpha, frame, 1 - alpha, 0, frame)
            glow_overlay = frame.copy()

        self.draw_corner_box(
            frame,
            box,
            color=color,
            thickness=cfg.BOX_THICKNESS,
            radius=cfg.CORNER_RADIUS,
        )

    def format_detection_label(self, class_name, track_id, confidence, box):
        """
        Tao nhan linh hoat theo kich thuoc box.

        Ly do:
        - Xe o xa rat nho, neu hien full text se bi chong nhau.
        - Xe o gan co the hien thi day du class + ID + confidence.
        """
        x1, y1, x2, y2 = box
        area = max(1, (x2 - x1) * (y2 - y1))

        if area < cfg.SMALL_BOX_AREA:
            return f"#{track_id}", 0.52
        if area < cfg.MEDIUM_BOX_AREA:
            return f"{class_name.upper()} #{track_id}", 0.58
        return f"{class_name.upper()} #{track_id}  {confidence:.2f}", cfg.LABEL_FONT_SCALE

    def draw_label(self, frame, text, anchor, color, font_scale):
        """
        Ve nhan class + ID tren bounding box.
        Day la phan rat quan trong khi thuyet trinh ve tracking.
        """
        text_size, _ = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_DUPLEX, font_scale, cfg.LABEL_THICKNESS
        )
        text_w, text_h = text_size
        x, y = anchor
        padding = 8

        box_top_left = (x, max(0, y - text_h - padding * 2))
        box_bottom_right = (x + text_w + padding * 2, y)
        self.draw_transparent_panel(frame, box_top_left, box_bottom_right, cfg.COLORS["panel"], 0.58)
        cv2.rectangle(
            frame,
            box_top_left,
            box_bottom_right,
            color,
            1,
            cv2.LINE_AA,
        )

        cv2.putText(
            frame,
            text,
            (x + padding, y - padding),
            cv2.FONT_HERSHEY_DUPLEX,
            font_scale,
            cfg.COLORS["text_shadow"],
            cfg.LABEL_THICKNESS + 2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            text,
            (x + padding, y - padding),
            cv2.FONT_HERSHEY_DUPLEX,
            font_scale,
            cfg.COLORS["text_primary"],
            cfg.LABEL_THICKNESS,
            cv2.LINE_AA,
        )

    def draw_trace(self, frame, track_id, center, color):
        """
        Ve duong di ngan phia sau xe de nguoi xem thay tracker dang bam doi tuong.
        """
        trace_points = self.track_trace[track_id]
        trace_points.append(center)

        if len(trace_points) > cfg.TRACE_LENGTH:
            trace_points.pop(0)

        for index in range(1, len(trace_points)):
            cv2.line(frame, trace_points[index - 1], trace_points[index], color, 2, cv2.LINE_AA)

    def draw_counting_line(self, frame):
        """
        Ve vach dem theo kieu gate:
        - Glow cyan phia sau
        - Duong line chinh mau cam do
        - Khong de text nam ngay trung tam vach vi de che xe
        """
        glow_overlay = frame.copy()
        cv2.line(
            glow_overlay,
            cfg.COUNT_LINE_START,
            cfg.COUNT_LINE_END,
            cfg.COLORS["line_glow"],
            10,
            cv2.LINE_AA,
        )
        cv2.addWeighted(glow_overlay, 0.18, frame, 0.82, 0, frame)

        cv2.line(
            frame,
            cfg.COUNT_LINE_START,
            cfg.COUNT_LINE_END,
            cfg.COLORS["line"],
            cfg.LINE_THICKNESS,
            cv2.LINE_AA,
        )

        cv2.circle(frame, cfg.COUNT_LINE_START, 7, cfg.COLORS["text_primary"], -1, cv2.LINE_AA)
        cv2.circle(frame, cfg.COUNT_LINE_END, 7, cfg.COLORS["text_primary"], -1, cv2.LINE_AA)

        tag_w = 170
        tag_h = 36
        x2, y2 = cfg.COUNT_LINE_END
        tag_left = max(20, x2 - tag_w)
        tag_top = max(cfg.HEADER_HEIGHT + 8, y2 - 52)
        tag_right = tag_left + tag_w
        tag_bottom = tag_top + tag_h

        self.draw_glass_panel(frame, (tag_left, tag_top), (tag_right, tag_bottom), alpha=0.48)
        cv2.putText(
            frame,
            "COUNT GATE",
            (tag_left + 18, tag_top + 24),
            cv2.FONT_HERSHEY_DUPLEX,
            0.62,
            cfg.COLORS["text_primary"],
            2,
            cv2.LINE_AA,
        )

    def draw_total_counter(self, frame):
        """
        Ve bang thong tin tong so xe.
        Co nen toi mo de dam bao do tuong phan cao tren moi nen video.
        """
        title = "TOTAL VEHICLES"
        value = str(self.total_count)

        title_size, _ = cv2.getTextSize(title, cv2.FONT_HERSHEY_DUPLEX, 0.72, 2)
        value_size, _ = cv2.getTextSize(
            value,
            cv2.FONT_HERSHEY_DUPLEX,
            cfg.TOTAL_FONT_SCALE + 0.6,
            cfg.TOTAL_TEXT_THICKNESS,
        )

        panel_w = max(cfg.COUNT_PANEL_WIDTH, max(title_size[0], value_size[0]) + 54)
        panel_h = 124
        top_left = (20, 20)
        bottom_right = (20 + panel_w, 20 + panel_h)

        self.draw_glass_panel(frame, top_left, bottom_right)

        cv2.putText(
            frame,
            title,
            (40, 56),
            cv2.FONT_HERSHEY_DUPLEX,
            0.72,
            cfg.COLORS["text_muted"],
            2,
            cv2.LINE_AA,
        )
        cv2.line(
            frame,
            (40, 72),
            (top_left[0] + panel_w - 26, 72),
            cfg.COLORS["panel_border"],
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            value,
            (40, 116),
            cv2.FONT_HERSHEY_DUPLEX,
            cfg.TOTAL_FONT_SCALE + 0.6,
            cfg.COLORS["panel_border"],
            cfg.TOTAL_TEXT_THICKNESS + 2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            value,
            (40, 116),
            cv2.FONT_HERSHEY_DUPLEX,
            cfg.TOTAL_FONT_SCALE + 0.6,
            cfg.COLORS["text_primary"],
            cfg.TOTAL_TEXT_THICKNESS,
            cv2.LINE_AA,
        )

    def draw_top_hud(self, frame):
        """
        Ve thanh thong tin tren cung.

        Muc tieu:
        - Tao cam giac he thong giam sat thong minh
        - Dua thong tin model/tracker ra ngoai vung quan sat cua xe
        """
        width = frame.shape[1]
        self.draw_glass_panel(frame, (18, 16), (width - 18, cfg.HEADER_HEIGHT), alpha=0.33)

        cv2.putText(
            frame,
            cfg.HUD_TITLE,
            (330, 48),
            cv2.FONT_HERSHEY_DUPLEX,
            1.0,
            cfg.COLORS["panel_border"],
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            cfg.HUD_SUBTITLE,
            (330, 78),
            cv2.FONT_HERSHEY_DUPLEX,
            0.58,
            cfg.COLORS["text_secondary"],
            1,
            cv2.LINE_AA,
        )

        right_text = f"TRACKER: {self.tracker.upper()}   CONF: {self.confidence:.2f}"
        text_size, _ = cv2.getTextSize(right_text, cv2.FONT_HERSHEY_DUPLEX, 0.52, 1)
        cv2.putText(
            frame,
            right_text,
            (width - text_size[0] - 38, 50),
            cv2.FONT_HERSHEY_DUPLEX,
            0.52,
            cfg.COLORS["text_muted"],
            1,
            cv2.LINE_AA,
        )

    def draw_footer_status(self, frame):
        """
        Ve thanh trang thai duoi cung gom frame, FPS, model va phim thoat.
        """
        height, width = frame.shape[:2]
        top = height - cfg.FOOTER_HEIGHT - 10
        self.draw_glass_panel(frame, (18, top), (width - 18, height - 10), alpha=0.28)

        left_text = (
            f"FRAME {self.frame_index:05d}   FPS {self.current_fps:05.1f}   "
            f"MODEL YOLOV8N   TARGET {','.join(name.upper() for name in cfg.TARGET_CLASS_NAMES)}"
        )
        cv2.putText(
            frame,
            left_text,
            (34, height - 22),
            cv2.FONT_HERSHEY_DUPLEX,
            0.5,
            cfg.COLORS["text_secondary"],
            1,
            cv2.LINE_AA,
        )

        exit_text = "PRESS Q TO EXIT"
        text_size, _ = cv2.getTextSize(exit_text, cv2.FONT_HERSHEY_DUPLEX, 0.5, 1)
        cv2.putText(
            frame,
            exit_text,
            (width - text_size[0] - 34, height - 22),
            cv2.FONT_HERSHEY_DUPLEX,
            0.5,
            cfg.COLORS["warning"],
            1,
            cv2.LINE_AA,
        )

    def process_detections(self, frame, result):
        """
        Xu ly toan bo detection/tracking tren 1 frame.

        Trinh tu:
        1. Lay box, class, track ID tu YOLO.
        2. Tinh tam box cho tung xe.
        3. So sanh vi tri cu - moi de xem co cat vach hay khong.
        4. Neu cat vach va chua tung dem thi tang bien tong.
        5. Ve trace, box, label len giao dien.
        """
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return

        xyxy_boxes = boxes.xyxy.cpu().numpy().astype(int)
        track_ids = boxes.id.cpu().numpy().astype(int)
        class_ids = boxes.cls.cpu().numpy().astype(int)
        confidences = boxes.conf.cpu().numpy()

        for box, track_id, class_id, confidence in zip(
            xyxy_boxes, track_ids, class_ids, confidences
        ):
            class_name = self.model.names[class_id]
            color = self.get_vehicle_color(class_name)
            center = self.get_box_center(box)
            x1, y1, x2, y2 = box
            box_area = max(1, (x2 - x1) * (y2 - y1))

            previous_center = self.track_history.get(track_id)
            if previous_center is not None and track_id not in self.counted_ids:
                if self.has_crossed_counting_line(previous_center, center):
                    self.total_count += 1
                    self.counted_ids.add(track_id)
                    self.logger.info(
                        "Da dem xe | track_id=%s | class=%s | tong=%s",
                        track_id,
                        class_name,
                        self.total_count,
                    )

            self.track_history[track_id] = center

            if box_area >= cfg.TRACE_MIN_BOX_AREA:
                self.draw_trace(frame, track_id, center, color)

            self.draw_neon_box(frame, box, color)
            cv2.circle(frame, center, 4, color, -1, cv2.LINE_AA)

            label_text, font_scale = self.format_detection_label(
                class_name, track_id, confidence, box
            )
            label_y = max(cfg.LABEL_MIN_Y, y1 - 8)
            label_x = x1
            if box_area < cfg.SMALL_BOX_AREA:
                label_x = min(frame.shape[1] - 90, x2 + 8)
                label_y = max(cfg.HEADER_HEIGHT + 4, y1 + 24)
            self.draw_label(frame, label_text, (label_x, label_y), color, font_scale)

    def analyze_frame(self, frame):
        """
        Phan tich nhanh 1 frame cho luong web (camera quet bien so).
        Van giu tracker + line crossing + tong dem theo thoi gian.
        """
        if frame is None:
            return {"ok": False, "message": "frame_none"}

        self.frame_index += 1
        frame = self.resize_frame(frame)

        results = self.model.track(
            source=frame,
            classes=self.target_class_ids,
            persist=True,
            tracker=self.tracker,
            conf=self.confidence,
            verbose=False,
        )
        result = results[0]
        prev_total = self.total_count
        self.process_detections(frame, result)

        detected_now = 0
        classes_now = {"car": 0, "bus": 0, "truck": 0}
        boxes = result.boxes
        if boxes is not None and boxes.cls is not None:
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            detected_now = len(cls_ids)
            for cid in cls_ids:
                cname = str(self.model.names.get(cid, "")).lower()
                if cname in classes_now:
                    classes_now[cname] += 1

        return {
            "ok": True,
            "frame_index": self.frame_index,
            "detected_now": detected_now,
            "classes_now": classes_now,
            "total_count": int(self.total_count),
            "new_crossings": int(self.total_count - prev_total),
            "tracker": self.tracker,
            "confidence": float(self.confidence),
            "count_line": {
                "start": cfg.COUNT_LINE_START,
                "end": cfg.COUNT_LINE_END,
            },
        }

    def build_output_path(self, video_path, output_path=None):
        """
        Tao ten file output tu dong neu nguoi dung khong truyen san.
        """
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            return output_path

        video_path = Path(video_path)
        generated_name = f"{video_path.stem}_counted.mp4"
        return cfg.OUTPUT_DIR / generated_name

    def create_writer(self, output_path, fps, frame_shape):
        """
        Tao doi tuong VideoWriter de luu ket qua.
        Tao muon sau khi co frame dau tien de chac chan dung kich thuoc.
        """
        height, width = frame_shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*cfg.OUTPUT_CODEC)
        return cv2.VideoWriter(str(output_path), fourcc, fps or 25, (width, height))

    def run(self, video_path, output_path=None, save_output=False, show_window=True):
        """
        Chay toan bo pipeline dem xe.

        video_path: video dau vao can phan tich.
        output_path: duong dan file video ket qua.
        save_output: co luu video sau xu ly hay khong.
        show_window: co hien cua so cv2.imshow hay khong.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Khong tim thay video: {video_path}")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(f"Khong mo duoc video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.logger.info("Bat dau phan tich video: %s", video_path)
        self.logger.info("Tong so frame cua video: %s", frame_count)
        self.logger.info(
            "Vach dem hien tai: %s -> %s", cfg.COUNT_LINE_START, cfg.COUNT_LINE_END
        )

        writer = None
        final_output_path = self.build_output_path(video_path, output_path)

        while True:
            success, frame = cap.read()
            if not success:
                break

            self.frame_index += 1
            now = time.perf_counter()
            delta = max(now - self._fps_timer, 1e-6)
            self.current_fps = 1.0 / delta
            self._fps_timer = now

            frame = self.resize_frame(frame)

            # model.track la trai tim cua he thong:
            # - Detect: tim cac xe trong khung hinh
            # - Track: gan cung mot ID cho cung mot xe qua nhieu frame
            results = self.model.track(
                source=frame,
                classes=self.target_class_ids,
                persist=True,
                tracker=self.tracker,
                conf=self.confidence,
                verbose=False,
            )

            result = results[0]
            self.process_detections(frame, result)
            self.draw_top_hud(frame)
            self.draw_counting_line(frame)
            self.draw_total_counter(frame)
            self.draw_footer_status(frame)

            if save_output:
                if writer is None:
                    writer = self.create_writer(final_output_path, fps, frame.shape)
                    self.logger.info("Dang luu video ket qua tai: %s", final_output_path)
                writer.write(frame)

            if show_window:
                cv2.imshow(cfg.WINDOW_NAME, frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    self.logger.info("Nguoi dung da dung chuong trinh bang phim q.")
                    break

        cap.release()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()

        self.logger.info("Xu ly xong video.")
        self.logger.info("Tong so xe da cat vach dem: %s", self.total_count)

        return {
            "video_path": str(video_path),
            "total_count": self.total_count,
            "saved_output": str(final_output_path) if save_output else None,
        }
