"""
Voting Service
Vote OCR results from multiple frames
"""
from collections import Counter
from typing import List, Dict, Optional
from Levenshtein import distance as levenshtein_distance

def vote_ocr_results(ocr_results: List[Dict]) -> Optional[Dict]:
    """
    Vote license plates from multiple OCR results
    
    Args:
        ocr_results: List of {
            "license_plate": str,
            "confidence": float,
            "frame_id": int,
            "quality_score": float
        }
    
    Returns:
        {
            "license_plate": str,
            "vote_count": int,
            "vote_percent": float,
            "total_frames": int,
            "avg_confidence": float
        }
    """
    # Filter valid results
    valid = [r for r in ocr_results if r.get("license_plate")]
    if not valid:
        return None
    
    # Count votes
    plates = [r["license_plate"] for r in valid]
    vote_counts = Counter(plates)
    
    # Get winner
    winner, count = vote_counts.most_common(1)[0]
    
    # Calculate average confidence for winning plate
    matching = [r for r in valid if r["license_plate"] == winner]
    avg_confidence = sum(r["confidence"] for r in matching) / len(matching)
    
    return {
        "license_plate": winner,
        "vote_count": count,
        "vote_percent": round(count / len(ocr_results) * 100, 2),
        "total_frames": len(ocr_results),
        "avg_confidence": round(avg_confidence, 4)
    }

def fuzzy_vote_ocr_results(ocr_results: List[Dict], threshold: int = 1) -> Optional[Dict]:
    """
    Vote with fuzzy matching for OCR errors
    
    Args:
        threshold: Max Levenshtein distance (default: 1)
    """
    valid = [r for r in ocr_results if r.get("license_plate")]
    if not valid:
        return None
    
    # Group similar plates
    groups = []
    for plate in [r["license_plate"] for r in valid]:
        found = False
        for group in groups:
            if levenshtein_distance(plate, group[0]) <= threshold:
                group.append(plate)
                found = True
                break
        if not found:
            groups.append([plate])
    
    # Find largest group
    largest_group = max(groups, key=len)
    winner = Counter(largest_group).most_common(1)[0][0]
    
    # Get matching results
    matching = [r for r in valid if levenshtein_distance(r["license_plate"], winner) <= threshold]
    avg_confidence = sum(r["confidence"] for r in matching) / len(matching)
    
    return {
        "license_plate": winner,
        "vote_count": len(largest_group),
        "vote_percent": round(len(largest_group) / len(ocr_results) * 100, 2),
        "total_frames": len(ocr_results),
        "avg_confidence": round(avg_confidence, 4)
    }
