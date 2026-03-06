import cv2
import numpy as np
import os
from datetime import datetime


class LicensePlateDetector:
    """Phát hiện biển số xe với vẽ zone và trích xuất"""
    
    def __init__(self):
        # Cấu hình tỉ lệ biển số VN
        self.MIN_RATIO = 2.0
        self.MAX_RATIO = 5.5
        self.MIN_AREA = 1500
        self.MAX_AREA = 50000
        
        # Tạo thư mục lưu kết quả
        self.output_dir = "detected_plates"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
    def preprocess(self, img):
        """Tiền xử lý ảnh để nổi bật biển số"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        denoised = cv2.bilateralFilter(gray, 11, 17, 17)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        thresh = cv2.adaptiveThreshold(
            enhanced, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 
            15, 5
        )
        return gray, thresh
    
    def morphology_ops(self, thresh):
        """Gom các ký tự thành 1 khối"""
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 5))
        morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        kernel2 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        morph = cv2.morphologyEx(morph, cv2.MORPH_OPEN, kernel2)
        return morph
    
    def filter_contours(self, contours, img_height, thresh):
        """Filter thông minh - lọc theo đặc trưng BSX"""
        candidates = []
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.MIN_AREA or area > self.MAX_AREA:
                continue
            
            x, y, w, h = cv2.boundingRect(cnt)
            ratio = w / float(h)
            if ratio < self.MIN_RATIO or ratio > self.MAX_RATIO:
                continue
            
            y_position = y / float(img_height)
            if y_position < 0.6 or y_position > 0.95:
                continue
            
            roi = thresh[y:y+h, x:x+w]
            edge_density = cv2.countNonZero(roi) / (w * h)
            if edge_density < 0.15 or edge_density > 0.7:
                continue
            
            rect = cv2.minAreaRect(cnt)
            box = cv2.boxPoints(rect)
            box_w = rect[1][0]
            box_h = rect[1][1]
            if box_w < box_h:
                box_w, box_h = box_h, box_w
            rectangularity = (w * h) / (box_w * box_h) if box_w * box_h > 0 else 0
            if rectangularity < 0.7:
                continue
            
            score = area * ratio * edge_density * rectangularity
            candidates.append({
                'contour': cnt,
                'bbox': (x, y, w, h),
                'score': score,
                'ratio': ratio,
                'area': area
            })
        
        candidates.sort(key=lambda c: c['score'], reverse=True)
        return candidates
    
    def draw_zone(self, img, bbox, label="License Plate"):
        """Vẽ zone (bounding box) với style đẹp"""
        x, y, w, h = bbox
        result = img.copy()
        
        # Vẽ khung chính (màu xanh lá dày)
        cv2.rectangle(result, (x, y), (x+w, y+h), (0, 255, 0), 3)
        
        # Vẽ góc trang trí (corner markers)
        corner_len = 20
        corner_thick = 4
        # Top-left
        cv2.line(result, (x, y), (x+corner_len, y), (0, 255, 255), corner_thick)
        cv2.line(result, (x, y), (x, y+corner_len), (0, 255, 255), corner_thick)
        # Top-right
        cv2.line(result, (x+w, y), (x+w-corner_len, y), (0, 255, 255), corner_thick)
        cv2.line(result, (x+w, y), (x+w, y+corner_len), (0, 255, 255), corner_thick)
        # Bottom-left
        cv2.line(result, (x, y+h), (x+corner_len, y+h), (0, 255, 255), corner_thick)
        cv2.line(result, (x, y+h), (x, y+h-corner_len), (0, 255, 255), corner_thick)
        # Bottom-right
        cv2.line(result, (x+w, y+h), (x+w-corner_len, y+h), (0, 255, 255), corner_thick)
        cv2.line(result, (x+w, y+h), (x+w, y+h-corner_len), (0, 255, 255), corner_thick)
        
        # Vẽ label box phía trên
        label_bg_h = 35
        cv2.rectangle(result, (x, y-label_bg_h), (x+w, y), (0, 255, 0), -1)
        cv2.putText(result, label, (x+5, y-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        
        # Vẽ thông tin kích thước
        info_text = f"{w}x{h}px"
        cv2.putText(result, info_text, (x, y+h+25), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        return result
    
    def save_plate(self, plate_img, original_img_path):
        """Lưu biển số đã trích xuất"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(original_img_path))[0]
        
        # Lưu biển số gốc
        plate_path = os.path.join(self.output_dir, f"{base_name}_plate_{timestamp}.jpg")
        cv2.imwrite(plate_path, plate_img)
        
        # Lưu biển số đã tăng cường (để OCR)
        gray_plate = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        _, enhanced = cv2.threshold(gray_plate, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        enhanced_path = os.path.join(self.output_dir, f"{base_name}_enhanced_{timestamp}.jpg")
        cv2.imwrite(enhanced_path, enhanced)
        
        return plate_path, enhanced_path
    
    def detect(self, img_path):
        """Phát hiện biển số xe với vẽ zone và trích xuất"""
        img = cv2.imread(img_path)
        if img is None:
            print(f"❌ Không đọc được ảnh: {img_path}")
            return None
        
        h, w = img.shape[:2]
        
        # Resize nếu ảnh quá lớn
        if w > 1000:
            scale = 1000 / w
            img = cv2.resize(img, None, fx=scale, fy=scale)
            h, w = img.shape[:2]
        
        # Tiền xử lý
        gray, thresh = self.preprocess(img)
        
        # Morphology
        morph = self.morphology_ops(thresh)
        
        # Tìm contours
        contours, _ = cv2.findContours(
            morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        # Filter thông minh
        candidates = self.filter_contours(contours, h, thresh)
        
        if len(candidates) > 0:
            # Lấy ứng viên tốt nhất
            best = candidates[0]
            x, y, w, h = best['bbox']
            
            # Vẽ zone lên ảnh gốc
            result_with_zone = self.draw_zone(img, best['bbox'])
            
            # Cắt biển số (mở rộng 1 chút để lấy đủ)
            padding = 5
            y1 = max(0, y - padding)
            y2 = min(img.shape[0], y + h + padding)
            x1 = max(0, x - padding)
            x2 = min(img.shape[1], x + w + padding)
            plate = img[y1:y2, x1:x2]
            
            # Lưu biển số
            plate_path, enhanced_path = self.save_plate(plate, img_path)
            
            print(f"✅ Phát hiện biển số thành công!")
            print(f"   📐 Tỉ lệ: {best['ratio']:.2f}")
            print(f"   📏 Diện tích: {best['area']:.0f}px²")
            print(f"   📍 Vị trí: ({x}, {y})")
            print(f"   💾 Đã lưu:")
            print(f"      - Biển số gốc: {plate_path}")
            print(f"      - Biển số tăng cường: {enhanced_path}")
            
            # Hiển thị kết quả
            cv2.imshow("1. Detected Zone", result_with_zone)
            cv2.imshow("2. Extracted Plate", plate)
            cv2.imshow("3. Preprocessed", thresh)
            cv2.imshow("4. Morphology", morph)
            
            print("\n⌨️  Nhấn phím bất kỳ để đóng cửa sổ...")
            
        else:
            print("❌ Không tìm thấy biển số")
            cv2.imshow("Result", img)
            cv2.imshow("Preprocessed", thresh)
        
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        
        return candidates


# SỬ DỤNG
if __name__ == "__main__":
    detector = LicensePlateDetector()
    
    # Phát hiện biển số
    print("🚗 Bắt đầu phát hiện biển số xe...")
    print("=" * 50)
    
    detector.detect("2.webp")
    
    print("\n" + "=" * 50)
    print("✨ Hoàn tất!")