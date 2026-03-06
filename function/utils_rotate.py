import numpy as np
import math
import cv2

# ========== ENHANCED CONTRAST ADJUSTMENT ==========
def changeContrast(img, clip_limit=3.0, tile_size=(8, 8)):
    """
    Enhanced contrast adjustment using CLAHE
    
    Args:
        img: input image
        clip_limit: contrast limiting threshold
        tile_size: size of grid for histogram equalization
    """
    if img is None or img.size == 0:
        return img
    
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel, a, b = cv2.split(lab)
    
    # Apply CLAHE to L-channel
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_size)
    cl = clahe.apply(l_channel)
    
    # Merge back
    limg = cv2.merge((cl, a, b))
    enhanced_img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    
    return enhanced_img


# ========== IMPROVED ROTATION ==========
def rotate_image(image, angle):
    """
    Rotate image by given angle with better border handling
    
    Args:
        image: input image
        angle: rotation angle in degrees
    """
    if image is None or image.size == 0:
        return image
    
    h, w = image.shape[:2]
    image_center = (w / 2, h / 2)
    
    # Get rotation matrix
    rot_mat = cv2.getRotationMatrix2D(image_center, angle, 1.0)
    
    # Calculate new image dimensions to avoid cropping
    abs_cos = abs(rot_mat[0, 0])
    abs_sin = abs(rot_mat[0, 1])
    
    new_w = int(h * abs_sin + w * abs_cos)
    new_h = int(h * abs_cos + w * abs_sin)
    
    # Adjust rotation matrix for new dimensions
    rot_mat[0, 2] += (new_w / 2) - image_center[0]
    rot_mat[1, 2] += (new_h / 2) - image_center[1]
    
    # Perform rotation with white background
    result = cv2.warpAffine(
        image, 
        rot_mat, 
        (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255)  # White background
    )
    
    return result


# ========== ADVANCED SKEW DETECTION ==========
def compute_skew(src_img, center_thres, use_probabilistic=True):
    """
    Compute skew angle of image using Hough Line Transform
    
    Args:
        src_img: source image
        center_thres: threshold for center filtering
        use_probabilistic: use Probabilistic Hough Transform (more robust)
    
    Returns:
        skew angle in degrees
    """
    if src_img is None or src_img.size == 0:
        return 0.0
    
    # Get image dimensions
    if len(src_img.shape) == 3:
        h, w, _ = src_img.shape
    elif len(src_img.shape) == 2:
        h, w = src_img.shape
    else:
        print('Unsupported image type')
        return 0.0
    
    # Preprocessing for better edge detection
    img = cv2.medianBlur(src_img, 3)
    
    # Adaptive Canny edge detection
    v = np.median(img)
    sigma = 0.33
    lower = int(max(0, (1.0 - sigma) * v))
    upper = int(min(255, (1.0 + sigma) * v))
    
    edges = cv2.Canny(
        img,
        threshold1=lower,
        threshold2=upper,
        apertureSize=3,
        L2gradient=True
    )
    
    # Detect lines using Probabilistic Hough Transform
    if use_probabilistic:
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=int(w * 0.3),  # Dynamic threshold based on width
            minLineLength=w / 2.5,    # Relaxed minimum line length
            maxLineGap=h / 2.0        # Relaxed max gap
        )
    else:
        # Standard Hough Transform (fallback)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, int(w * 0.4))
    
    if lines is None or len(lines) == 0:
        return 0.0
    
    # Filter lines by position (focus on horizontal lines)
    valid_lines = []
    
    for line in lines:
        if use_probabilistic:
            x1, y1, x2, y2 = line[0]
            center_y = (y1 + y2) / 2
            
            # Filter by center threshold
            if center_thres == 1 and center_y < h * 0.15:
                continue
            
            # Calculate angle
            angle = np.arctan2(y2 - y1, x2 - x1)
            
            # Only consider nearly horizontal lines (within ±30 degrees)
            if abs(angle) <= np.pi / 6:  # 30 degrees in radians
                valid_lines.append(angle)
        else:
            rho, theta = line[0]
            angle = theta - np.pi / 2
            if abs(angle) <= np.pi / 6:
                valid_lines.append(angle)
    
    if len(valid_lines) == 0:
        return 0.0
    
    # Use median angle for robustness (less sensitive to outliers)
    median_angle = np.median(valid_lines)
    
    # Convert to degrees
    angle_deg = median_angle * 180 / np.pi
    
    # Clamp angle to reasonable range
    angle_deg = np.clip(angle_deg, -15, 15)
    
    return angle_deg


# ========== MULTI-ANGLE DESKEW ==========
def deskew(src_img, change_cons, center_thres, try_multiple_angles=True):
    """
    Deskew image with optional multi-angle attempt
    
    Args:
        src_img: source image
        change_cons: 1 to apply contrast enhancement first
        center_thres: center threshold for line filtering
        try_multiple_angles: try multiple deskew methods
    
    Returns:
        deskewed image
    """
    if src_img is None or src_img.size == 0:
        return src_img
    
    # Method 1: With contrast enhancement
    if change_cons == 1:
        enhanced = changeContrast(src_img)
        angle = compute_skew(enhanced, center_thres)
        result = rotate_image(src_img, angle)
        
        # If angle is too extreme, try without enhancement
        if abs(angle) > 12 and try_multiple_angles:
            angle2 = compute_skew(src_img, center_thres)
            if abs(angle2) < abs(angle):
                result = rotate_image(src_img, angle2)
        
        return result
    else:
        # Method 2: Direct deskew
        angle = compute_skew(src_img, center_thres)
        return rotate_image(src_img, angle)


# ========== ADDITIONAL PREPROCESSING OPTIONS ==========
def auto_rotate_if_needed(img, max_angle=15):
    """
    Automatically detect and rotate image if skewed
    
    Args:
        img: input image
        max_angle: maximum rotation angle to apply
    
    Returns:
        (rotated_image, angle_applied)
    """
    angle = compute_skew(img, center_thres=0)
    
    if abs(angle) < 1.0:
        # Already straight enough
        return img, 0.0
    
    if abs(angle) > max_angle:
        # Too extreme, likely wrong detection
        return img, 0.0
    
    rotated = rotate_image(img, angle)
    return rotated, angle


def deskew_aggressive(src_img):
    """
    Aggressive deskew that tries multiple methods and picks the best
    
    Returns: best deskewed image
    """
    if src_img is None or src_img.size == 0:
        return src_img
    
    candidates = []
    
    # Method 1: Standard deskew
    angle1 = compute_skew(src_img, center_thres=0)
    result1 = rotate_image(src_img, angle1)
    candidates.append((result1, abs(angle1)))
    
    # Method 2: With contrast
    enhanced = changeContrast(src_img)
    angle2 = compute_skew(enhanced, center_thres=1)
    result2 = rotate_image(src_img, angle2)
    candidates.append((result2, abs(angle2)))
    
    # Method 3: Try negative angle
    angle3 = -angle1
    result3 = rotate_image(src_img, angle3)
    candidates.append((result3, abs(angle3)))
    
    # Pick the one with smallest rotation (most likely correct)
    best = min(candidates, key=lambda x: x[1])
    
    return best[0]


# ========== PERSPECTIVE CORRECTION (BONUS) ==========
def correct_perspective(img):
    """
    Advanced: Correct perspective distortion in license plate
    Useful for plates captured at an angle
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    
    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return img
    
    # Find largest rectangular contour
    largest_contour = max(contours, key=cv2.contourArea)
    
    # Approximate to polygon
    epsilon = 0.02 * cv2.arcLength(largest_contour, True)
    approx = cv2.approxPolyDP(largest_contour, epsilon, True)
    
    if len(approx) == 4:
        # Found quadrilateral - apply perspective transform
        pts = approx.reshape(4, 2).astype(np.float32)
        
        # Order points: top-left, top-right, bottom-right, bottom-left
        rect = order_points(pts)
        
        # Calculate dimensions of new image
        width = max(
            np.linalg.norm(rect[0] - rect[1]),
            np.linalg.norm(rect[2] - rect[3])
        )
        height = max(
            np.linalg.norm(rect[0] - rect[3]),
            np.linalg.norm(rect[1] - rect[2])
        )
        
        dst = np.array([
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1]
        ], dtype=np.float32)
        
        # Compute perspective transform matrix
        M = cv2.getPerspectiveTransform(rect, dst)
        
        # Apply transformation
        warped = cv2.warpPerspective(img, M, (int(width), int(height)))
        
        return warped
    
    return img


def order_points(pts):
    """Order points in clockwise order starting from top-left"""
    rect = np.zeros((4, 2), dtype=np.float32)
    
    # Sum: top-left has smallest sum, bottom-right has largest
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    
    # Diff: top-right has smallest diff, bottom-left has largest
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    
    return rect