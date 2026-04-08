"""
Image Quality Scoring Service
Calculate quality metrics for images
"""
import cv2
import numpy as np
from typing import Dict

def calculate_quality_score(image: np.ndarray) -> Dict[str, float]:
    """
    Calculate image quality score (0-100)
    
    Metrics:
    - Sharpness (40%)
    - Brightness (20%)
    - Contrast (20%)
    - Noise (10%)
    - Edge density (10%)
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    
    # 1. Sharpness (Variance of Laplacian) - 40%
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    sharpness = min(laplacian_var / 100 * 40, 40)
    
    # 2. Brightness (Mean pixel value) - 20%
    brightness_mean = np.mean(gray)
    if 80 <= brightness_mean <= 180:
        brightness = 20
    elif brightness_mean < 80:
        brightness = (brightness_mean / 80) * 20
    else:  # > 180
        brightness = max(0, 20 - (brightness_mean - 180) / 10)
    
    # 3. Contrast (Std deviation) - 20%
    contrast_std = np.std(gray)
    contrast = min(contrast_std / 40 * 20, 20)
    
    # 4. Noise (Laplacian mean) - 10%
    noise_estimate = np.mean(np.abs(cv2.Laplacian(gray, cv2.CV_64F)))
    noise = max(0, 10 - (noise_estimate / 50 * 10))
    
    # 5. Edge density (Canny edges) - 10%
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.sum(edges > 0) / edges.size
    edge_score = min(edge_density * 100 / 30 * 10, 10)
    
    # Total score
    total = sharpness + brightness + contrast + noise + edge_score
    
    return {
        "overall_score": round(total, 2),
        "sharpness": round(sharpness, 2),
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "noise": round(noise, 2),
        "edge_density": round(edge_score, 2)
    }

def is_good_quality(image: np.ndarray, threshold: float = 70.0) -> bool:
    """Check if image meets quality threshold"""
    score = calculate_quality_score(image)
    return score["overall_score"] >= threshold
