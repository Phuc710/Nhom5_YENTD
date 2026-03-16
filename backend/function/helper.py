import math
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

def linear_equation(x1, y1, x2, y2):
    """Calculate linear equation coefficients from two points"""
    if x2 == x1:
        return None, None
    b = y1 - (y2 - y1) * x1 / (x2 - x1)
    a = (y1 - b) / x1
    return a, b

def check_point_linear(x, y, x1, y1, x2, y2):
    """Check if point is on line defined by two points"""
    a, b = linear_equation(x1, y1, x2, y2)
    if a is None:
        return False
    y_pred = a*x+b
    return math.isclose(y_pred, y, abs_tol=5)


def format_plate_characters(char_detections: Iterable[Dict[str, Any]]) -> str:
    """Ghep ky tu bien so tu danh sach detect OCR theo logic 1 dong / 2 dong."""
    detections = list(char_detections or [])
    if not detections:
        return "unknown"

    center_list: List[List[Any]] = []
    confidences: List[float] = []

    for item in detections:
        x1 = float(item.get("x1", 0))
        y1 = float(item.get("y1", 0))
        x2 = float(item.get("x2", 0))
        y2 = float(item.get("y2", 0))
        label = str(item.get("label", "")).strip().upper()
        confidence = float(item.get("conf", 0.0) or 0.0)

        if not label:
            continue

        x_c = (x1 + x2) / 2.0
        y_c = (y1 + y2) / 2.0
        confidences.append(confidence)
        center_list.append([x_c, y_c, label, confidence])

    if not center_list:
        return "unknown"

    avg_confidence = sum(confidences) / max(len(confidences), 1)
    if avg_confidence < 0.2:
        return "unknown"

    lp_type = "1"
    l_point = min(center_list, key=lambda item: item[0])
    r_point = max(center_list, key=lambda item: item[0])

    off_line_count = 0
    for item in center_list:
        if l_point[0] != r_point[0]:
            if not check_point_linear(item[0], item[1], l_point[0], l_point[1], r_point[0], r_point[1]):
                off_line_count += 1

    if off_line_count > len(center_list) * 0.3:
        lp_type = "2"

    license_plate = ""

    if lp_type == "2":
        y_values = [item[1] for item in center_list]
        y_threshold = np.median(y_values)

        line_1 = [item for item in center_list if item[1] < y_threshold]
        line_2 = [item for item in center_list if item[1] >= y_threshold]
        line_1.sort(key=lambda item: item[0])
        line_2.sort(key=lambda item: item[0])

        for item in line_1:
            license_plate += item[2]
        if line_1 and line_2:
            license_plate += "-"
        for item in line_2:
            license_plate += item[2]
    else:
        center_list.sort(key=lambda item: item[0])
        for item in center_list:
            license_plate += item[2]

    license_plate = _sanitize_plate_text(license_plate)
    if _is_valid_plate_text(license_plate):
        return license_plate
    return "unknown"


def _sanitize_plate_text(license_plate: Optional[str]) -> str:
    valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")
    normalized = "".join(char for char in str(license_plate or "").upper() if char in valid_chars)
    return normalized.strip("-")


def _is_valid_plate_text(license_plate: str) -> bool:
    if not license_plate:
        return False
    plate_no_dash = license_plate.replace("-", "")
    if len(plate_no_dash) < 6 or len(plate_no_dash) > 10:
        return False
    return plate_no_dash.isalnum()

def read_plate(yolo_license_plate, im):
    """Detect and read characters from license plate image with improved logic"""
    try:
        results = yolo_license_plate(im)
        bb_list = results.pandas().xyxy[0].values.tolist()
        
        # Validate detection count (Vietnamese plates: 7-10 characters)
        if len(bb_list) == 0:
            return "unknown"
        
        # Allow more flexibility for detection count
        if len(bb_list) < 6 or len(bb_list) > 11:
            return "unknown"
        
        char_detections = [
            {
                "x1": bb[0],
                "y1": bb[1],
                "x2": bb[2],
                "y2": bb[3],
                "conf": bb[4] if len(bb) > 4 else 1.0,
                "label": str(bb[-1]),
            }
            for bb in bb_list
        ]
        return format_plate_characters(char_detections)
        
    except Exception as e:
        print(f"Error in read_plate: {e}")
        return "unknown"
