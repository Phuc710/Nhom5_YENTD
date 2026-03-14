"""
voting_service.py — Voting OCR kết quả từ nhiều frame

Hai chiến lược:
  vote_ocr_results       — Đơn giản: đếm tần suất biển số
  fuzzy_vote_ocr_results — Nâng cao: nhóm biển số gần nhau (Levenshtein ≤ threshold)
                           để chịu được lỗi OCR ký tự đơn (0↔O, 1↔I, ...)
"""
from collections import Counter
from typing import Dict, List, Optional

from Levenshtein import distance as levenshtein_distance


def vote_ocr_results(ocr_results: List[Dict]) -> Optional[Dict]:
    """
    Vote biển số từ nhiều kết quả OCR (đếm trực tiếp, không fuzzy).

    Input:  List[{"license_plate": str, "confidence": float, "quality_score": float}]
    Output: {"license_plate", "vote_count", "vote_percent", "total_frames", "avg_confidence"}
    """
    valid = [r for r in ocr_results if r.get("license_plate")]
    if not valid:
        return None

    vote_counts = Counter(r["license_plate"] for r in valid)
    winner, count = vote_counts.most_common(1)[0]
    matching = [r for r in valid if r["license_plate"] == winner]
    avg_conf = sum(r["confidence"] for r in matching) / len(matching)

    return {
        "license_plate": winner,
        "vote_count": count,
        "vote_percent": round(count / len(ocr_results) * 100, 2),
        "total_frames": len(ocr_results),
        "avg_confidence": round(avg_conf, 4),
    }


def fuzzy_vote_ocr_results(ocr_results: List[Dict], threshold: int = 1) -> Optional[Dict]:
    """
    Vote biển số với fuzzy matching (Levenshtein distance ≤ threshold).
    Giải quyết lỗi OCR đơn ký tự: 51A-1234 vs 5IA-1234, 30K-5678 vs 30K-5B78...

    threshold=1: Chịu được 1 ký tự sai/nhầm (mặc định khuyến nghị)
    threshold=2: Chịu được 2 ký tự (chỉ dùng nếu OCR chất lượng thấp)
    """
    valid = [r for r in ocr_results if r.get("license_plate")]
    if not valid:
        return None

    plates = [r["license_plate"] for r in valid]

    # Nhóm các biển số gần nhau (greedy grouping — O(n²) nhưng n nhỏ, tối đa vài chục)
    groups: List[List[str]] = []
    for plate in plates:
        matched_group = None
        for group in groups:
            if levenshtein_distance(plate, group[0]) <= threshold:
                matched_group = group
                break
        if matched_group is not None:
            matched_group.append(plate)
        else:
            groups.append([plate])

    # Nhóm lớn nhất = biển số xuất hiện nhiều nhất (kể cả lỗi nhỏ)
    largest_group = max(groups, key=len)
    winner = Counter(largest_group).most_common(1)[0][0]

    matching = [r for r in valid if levenshtein_distance(r["license_plate"], winner) <= threshold]
    avg_conf = sum(r["confidence"] for r in matching) / len(matching)

    return {
        "license_plate": winner,
        "vote_count": len(largest_group),
        "vote_percent": round(len(largest_group) / len(ocr_results) * 100, 2),
        "total_frames": len(ocr_results),
        "avg_confidence": round(avg_conf, 4),
    }
