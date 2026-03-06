"""
ESP32-S3 Camera Stream + License Plate Detection
Kết hợp camera stream từ ESP32 với YOLO detection
"""

import cv2
import torch
import numpy as np
import function.helper as helper
import time
import threading
from queue import Queue
from collections import Counter

# ========== CONFIG ==========
# ESP32 Settings
ESP32_IP = "192.168.1.173"  # Thay đổi IP này theo ESP32 của bạn
STREAM_URL = f"http://{ESP32_IP}/stream"

# Zone settings
ZONE_TOP = 0.25        # 25% from top
ZONE_BOTTOM = 0.75     # 75% from top
ENABLE_ZONE = True     # Set False to disable zone filtering

# OCR settings
RESIZE_FACTOR = 2.5    # Resize crop image by this factor
ENABLE_PREPROCESSING = True
MIN_CONFIDENCE_CHARS = 7  # Minimum characters for valid plate

# Performance settings
MAX_OCR_WORKERS = 2
OCR_QUEUE_SIZE = 5

# ========== DEVICE SETUP ==========
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"🎯 Device: {device}")

# ========== LOAD MODELS ==========
print("🔄 Loading models...")
yolo_LP_detect = torch.hub.load('ultralytics/yolov5', 'custom', 
                                 path='model/LP_detector_nano_61.pt', force_reload=False)
yolo_LP_detect.conf = 0.4
yolo_LP_detect.iou = 0.45

yolo_license_plate = torch.hub.load('ultralytics/yolov5', 'custom', 
                                     path='model/LP_ocr_nano_62.pt', force_reload=False)
yolo_license_plate.conf = 0.5

yolo_LP_detect.to(device)
yolo_license_plate.to(device)
print("✅ Models loaded!\n")


# ========== PREPROCESSING ==========
def preprocess_for_ocr(image):
    """
    Lightweight preprocessing for better OCR
    """
    if image is None or image.size == 0:
        return image
    
    h, w = image.shape[:2]
    
    # Step 1: Resize up (CRITICAL for OCR accuracy)
    target_w = int(w * RESIZE_FACTOR)
    target_h = int(h * RESIZE_FACTOR)
    resized = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
    
    if not ENABLE_PREPROCESSING:
        return resized
    
    # Step 2: Denoise (light)
    denoised = cv2.fastNlMeansDenoisingColored(resized, None, 10, 10, 7, 21)
    
    # Step 3: Convert to grayscale
    if len(denoised.shape) == 3:
        gray = cv2.cvtColor(denoised, cv2.COLOR_BGR2GRAY)
    else:
        gray = denoised
    
    # Step 4: Sharpen
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(gray, -1, kernel)
    
    # Step 5: CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(sharpened)
    
    # Convert back to BGR for YOLO
    final = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
    
    return final


# ========== ASYNC OCR PROCESSOR ==========
class AsyncOCRProcessor:
    def __init__(self, ocr_model, max_workers=2):
        self.ocr_model = ocr_model
        self.task_queue = Queue(maxsize=OCR_QUEUE_SIZE)
        self.result_queue = Queue()
        self.workers = []
        self.running = True
        
        for i in range(max_workers):
            worker = threading.Thread(target=self._worker, daemon=True)
            worker.start()
            self.workers.append(worker)
        
        print(f"🔧 Started {max_workers} OCR workers")
    
    def _worker(self):
        while self.running:
            try:
                task = self.task_queue.get(timeout=0.5)
                if task is None:
                    break
                
                frame_id, crop_img, bbox = task
                
                # Preprocess
                processed = preprocess_for_ocr(crop_img)
                
                # OCR
                lp = helper.read_plate(self.ocr_model, processed)
                
                # Validate result
                if lp != "unknown" and len(lp.replace("-", "")) >= MIN_CONFIDENCE_CHARS:
                    self.result_queue.put((frame_id, lp, bbox))
                
                self.task_queue.task_done()
            except:
                continue
    
    def submit(self, frame_id, crop_img, bbox):
        try:
            self.task_queue.put_nowait((frame_id, crop_img, bbox))
            return True
        except:
            return False
    
    def get_results(self):
        results = []
        while not self.result_queue.empty():
            try:
                results.append(self.result_queue.get_nowait())
            except:
                break
        return results
    
    def stop(self):
        self.running = False
        for _ in self.workers:
            self.task_queue.put(None)
        for worker in self.workers:
            worker.join(timeout=2)


# ========== PLATE VOTING SYSTEM ==========
class PlateVotingSystem:
    """
    Collect multiple readings and vote for most common result
    """
    def __init__(self, window_size=10):
        self.window_size = window_size
        self.recent_plates = []
    
    def add(self, plate):
        self.recent_plates.append(plate)
        if len(self.recent_plates) > self.window_size:
            self.recent_plates.pop(0)
    
    def get_consensus(self, min_votes=2):
        """Get plate with at least min_votes"""
        if not self.recent_plates:
            return None
        
        counter = Counter(self.recent_plates)
        most_common = counter.most_common(1)[0]
        
        if most_common[1] >= min_votes:
            return most_common[0]
        return None
    
    def get_all_unique(self):
        return Counter(self.recent_plates)


# ========== MAIN DETECTION FROM ESP32 STREAM ==========
def esp32_detect():
    """
    Detect license plates from ESP32 camera stream
    """
    
    print("=" * 60)
    print("ESP32-S3 Camera + License Plate Detection")
    print("=" * 60)
    print(f"📡 ESP32 IP: {ESP32_IP}")
    print(f"🔗 Stream URL: {STREAM_URL}")
    print(f"🎯 Device: {device}")
    print("\nPhím tắt:")
    print("  [q] - Thoát")
    print("  [s] - Lưu ảnh")
    print("  [r] - Kết nối lại")
    print("  [z] - Bật/tắt zone detection")
    print("=" * 60)
    
    # Connect to ESP32
    print(f"\n🔄 Đang kết nối đến ESP32...")
    cap = cv2.VideoCapture(STREAM_URL)
    
    if not cap.isOpened():
        print("❌ Không thể kết nối đến ESP32!")
        print("\nKiểm tra:")
        print("  1. ESP32 đã flash code và đang chạy?")
        print("  2. IP address đúng chưa? (Hiện tại: {})".format(ESP32_IP))
        print("  3. Cùng mạng WiFi không?")
        print("\n💡 Tip: Mở http://{} trên trình duyệt để kiểm tra".format(ESP32_IP))
        return
    
    print("✅ Kết nối ESP32 thành công!\n")
    
    # Get stream info
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Calculate zone
    zone_top_y = int(height * ZONE_TOP)
    zone_bottom_y = int(height * ZONE_BOTTOM)
    
    # Initialize
    ocr_processor = AsyncOCRProcessor(yolo_license_plate, max_workers=MAX_OCR_WORKERS)
    voting_system = PlateVotingSystem(window_size=15)
    
    global ENABLE_ZONE
    
    print(f"📹 Stream: {width}x{height}")
    if ENABLE_ZONE:
        print(f"🎯 Detection zone: {zone_top_y}px - {zone_bottom_y}px")
    print("🎬 Starting detection...\n")
    
    frame_count = 0
    plates_found = []
    
    # FPS tracking
    fps_time = time.time()
    fps_counter = 0
    current_fps = 0
    
    # Display buffer
    display_results = {}  # {frame_id: [(bbox, plate), ...]}
    
    # Create TWO separate windows
    cv2.namedWindow('ESP32 Camera', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('ESP32 Camera', 800, 600)
    
    cv2.namedWindow('Detection Info', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Detection Info', 400, 600)
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("⚠ Mất kết nối hoặc không nhận được frame")
                print("🔄 Thử kết nối lại...")
                cap.release()
                time.sleep(2)
                cap = cv2.VideoCapture(STREAM_URL)
                if not cap.isOpened():
                    print("❌ Không thể kết nối lại!")
                    break
                continue
            
            frame_count += 1
            fps_counter += 1
            
            if time.time() - fps_time > 1:
                current_fps = fps_counter
                fps_counter = 0
                fps_time = time.time()
            
            # ========== DRAW ZONE ==========
            if ENABLE_ZONE:
                cv2.line(frame, (0, zone_top_y), (width, zone_top_y), (255, 0, 0), 2)
                cv2.line(frame, (0, zone_bottom_y), (width, zone_bottom_y), (0, 255, 0), 2)
                overlay = frame.copy()
                cv2.rectangle(overlay, (0, zone_top_y), (width, zone_bottom_y), (0, 255, 255), -1)
                cv2.addWeighted(overlay, 0.08, frame, 0.92, 0, frame)
            
            # ========== DETECT ==========
            with torch.no_grad():
                plates = yolo_LP_detect(frame, size=416)
                list_plates = plates.pandas().xyxy[0].values.tolist()
            
            # ========== PROCESS ==========
            for plate in list_plates:
                x, y = int(plate[0]), int(plate[1])
                w = int(plate[2] - x)
                h = int(plate[3] - y)
                conf = plate[4]
                
                if w < 30 or h < 10:
                    continue
                
                center_y = y + h // 2
                
                # Check zone
                if ENABLE_ZONE:
                    in_zone = zone_top_y <= center_y <= zone_bottom_y
                    if not in_zone:
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (128, 128, 128), 1)
                        continue
                
                # In zone - process
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                
                # Crop with padding
                pad_x, pad_y = int(w * 0.15), int(h * 0.2)
                x1 = max(0, x - pad_x)
                y1 = max(0, y - pad_y)
                x2 = min(width, x + w + pad_x)
                y2 = min(height, y + h + pad_y)
                
                crop_img = frame[y1:y2, x1:x2].copy()
                
                if crop_img.shape[0] >= 20 and crop_img.shape[1] >= 40:
                    ocr_processor.submit(frame_count, crop_img, (x, y, w, h))
            
            # ========== GET RESULTS ==========
            results = ocr_processor.get_results()
            
            for frame_id, lp, bbox in results:
                plates_found.append(lp)
                voting_system.add(lp)
                print(f"✅ Frame {frame_id}: {lp}")
                
                if frame_id not in display_results:
                    display_results[frame_id] = []
                display_results[frame_id].append((bbox, lp))
            
            # ========== DISPLAY RESULTS ==========
            for fid in list(display_results.keys()):
                if frame_count - fid > 20:
                    del display_results[fid]
                else:
                    for (x, y, w, h), lp in display_results[fid]:
                        cv2.putText(frame, lp, (x, y+h+25), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            
            # ========== DISPLAY 1: CAMERA VIEW (Clean) ==========
            # Only show detection boxes and labels on camera
            cv2.imshow('ESP32 Camera', frame)
            
            # ========== DISPLAY 2: INFO PANEL (Separate Window) ==========
            # Create info panel as separate image
            panel_width = 400
            panel_height = 600
            panel = np.zeros((panel_height, panel_width, 3), dtype=np.uint8)
            
            # Background gradient
            for i in range(panel_height):
                intensity = int(30 + (i / panel_height) * 20)
                panel[i, :] = (intensity, intensity, intensity)
            
            # Header with gradient
            header_height = 80
            for i in range(header_height):
                intensity = int(60 - (i / header_height) * 20)
                panel[i, :] = (intensity, intensity, 80)
            
            cv2.putText(panel, "ESP32", (20, 35), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 100), 3)
            cv2.putText(panel, "DETECTION", (20, 65), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
            
            # Stats section
            y_pos = 110
            
            # FPS with icon
            cv2.circle(panel, (30, y_pos - 10), 8, (0, 255, 255), -1)
            cv2.putText(panel, f"FPS: {current_fps}", (50, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            y_pos += 45
            
            # Frame count
            cv2.circle(panel, (30, y_pos - 10), 8, (255, 255, 255), -1)
            cv2.putText(panel, f"Frame: {frame_count}", (50, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            y_pos += 45
            
            # Queue status with color indicator
            queue_size = ocr_processor.task_queue.qsize()
            queue_color = (0, 255, 0) if queue_size < 3 else (0, 165, 255)
            cv2.circle(panel, (30, y_pos - 10), 8, queue_color, -1)
            cv2.putText(panel, f"Queue: {queue_size}/{OCR_QUEUE_SIZE}", (50, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, queue_color, 2)
            y_pos += 45
            
            # Detected plates
            cv2.circle(panel, (30, y_pos - 10), 8, (255, 100, 255), -1)
            cv2.putText(panel, f"Detected: {len(plates_found)}", (50, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 100, 255), 2)
            y_pos += 60
            
            # Separator line
            cv2.line(panel, (20, y_pos), (panel_width - 20, y_pos), (100, 100, 100), 2)
            y_pos += 40
            
            # Consensus section (highlighted)
            consensus = voting_system.get_consensus(min_votes=3)
            if consensus:
                # Green background box
                cv2.rectangle(panel, (15, y_pos - 35), (panel_width - 15, y_pos + 45), (0, 80, 0), -1)
                cv2.rectangle(panel, (15, y_pos - 35), (panel_width - 15, y_pos + 45), (0, 255, 0), 2)
                
                cv2.putText(panel, "RESULT:", (25, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
                cv2.putText(panel, consensus, (25, y_pos + 35), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3)
                y_pos += 80
            else:
                cv2.putText(panel, "RESULT:", (25, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 2)
                cv2.putText(panel, "Waiting...", (25, y_pos + 35), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 100), 1)
                y_pos += 80
            
            # Zone status
            y_pos += 20
            zone_text = "ENABLED" if ENABLE_ZONE else "DISABLED"
            zone_color = (0, 255, 0) if ENABLE_ZONE else (0, 0, 255)
            cv2.circle(panel, (30, y_pos - 10), 8, zone_color, -1)
            cv2.putText(panel, f"Zone: {zone_text}", (50, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, zone_color, 2)
            y_pos += 50
            
            # Recent detections section
            cv2.line(panel, (20, y_pos), (panel_width - 20, y_pos), (100, 100, 100), 2)
            y_pos += 35
            cv2.putText(panel, "RECENT DETECTIONS:", (25, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
            y_pos += 30
            
            if plates_found:
                counter = Counter(plates_found)
                for i, (plate, count) in enumerate(counter.most_common(5), 1):
                    if y_pos > panel_height - 150:
                        break
                    
                    # Draw bar graph
                    bar_width = int((count / max(counter.values())) * 200)
                    cv2.rectangle(panel, (120, y_pos - 18), (120 + bar_width, y_pos - 5), (80, 80, 80), -1)
                    
                    cv2.putText(panel, f"{i}. {plate}", (30, y_pos), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
                    cv2.putText(panel, f"({count}x)", (330, y_pos), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
                    y_pos += 28
            else:
                cv2.putText(panel, "No plates yet...", (30, y_pos), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
            
            # Controls section at bottom
            bottom_y = panel_height - 100
            cv2.line(panel, (20, bottom_y), (panel_width - 20, bottom_y), (100, 100, 100), 2)
            bottom_y += 25
            cv2.putText(panel, "CONTROLS:", (25, bottom_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 2)
            bottom_y += 22
            cv2.putText(panel, "[Q] Quit      [S] Save", (30, bottom_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 120), 1)
            bottom_y += 20
            cv2.putText(panel, "[R] Reconnect [Z] Zone", (30, bottom_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 120), 1)
            
            cv2.imshow('Detection Info', panel)
            
            # ========== KEY HANDLING ==========
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                print("\n👋 Thoát chương trình...")
                break
                
            elif key == ord('s'):
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"esp32_capture_{timestamp}.jpg"
                cv2.imwrite(filename, frame)
                print(f"📸 Đã lưu: {filename}")
                
            elif key == ord('r'):
                print("\n🔄 Đang kết nối lại ESP32...")
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(STREAM_URL)
                if cap.isOpened():
                    print("✅ Kết nối lại thành công!")
                    frame_count = 0
                else:
                    print("❌ Không thể kết nối lại!")
                    break
            
            elif key == ord('z'):
                ENABLE_ZONE = not ENABLE_ZONE
                status = "BẬT" if ENABLE_ZONE else "TẮT"
                print(f"🎯 Zone detection: {status}")
    
    except KeyboardInterrupt:
        print("\n\n⛔ Dừng bởi người dùng (Ctrl+C)")
        
    finally:
        ocr_processor.stop()
        cap.release()
        cv2.destroyAllWindows()
        
        # ========== SUMMARY ==========
        print(f"\n{'='*60}")
        print(f"📊 RESULTS:")
        print(f"   Frames: {frame_count} | Plates: {len(plates_found)}")
        
        if plates_found:
            print(f"\n📋 Detected License Plates:")
            counter = Counter(plates_found)
            for i, (plate, count) in enumerate(counter.most_common(10), 1):
                percentage = (count / len(plates_found)) * 100
                print(f"   {i}. {plate:15s} ({count:3d}x = {percentage:5.1f}%)")
            
            # Show consensus
            top_plate = counter.most_common(1)[0]
            if top_plate[1] >= 3:
                print(f"\n🏆 FINAL RESULT: {top_plate[0]} (confidence: {top_plate[1]} detections)")
        else:
            print("\n⚠️ Không phát hiện biển số nào")
        
        print(f"{'='*60}\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='ESP32 License Plate Detection')
    parser.add_argument('--ip', type=str, default='192.168.1.173', 
                       help='ESP32 IP address')
    parser.add_argument('--no-zone', action='store_true', 
                       help='Disable zone filtering')
    parser.add_argument('--no-preprocess', action='store_true', 
                       help='Disable preprocessing')
    
    args = parser.parse_args()
    
    ESP32_IP = args.ip
    STREAM_URL = f"http://{ESP32_IP}/stream"
    ENABLE_ZONE = not args.no_zone
    ENABLE_PREPROCESSING = not args.no_preprocess
    
    print(f"""
╔══════════════════════════════════════════════════════════╗
║   ESP32-S3 Camera + License Plate Detection System      ║
║   Powered by YOLOv5 + OpenCV                            ║
╚══════════════════════════════════════════════════════════╝

📡 ESP32 IP: {ESP32_IP}
🔗 Stream: {STREAM_URL}
🎯 Zone Detection: {'Enabled' if ENABLE_ZONE else 'Disabled'}
🖼️  Preprocessing: {'Enabled' if ENABLE_PREPROCESSING else 'Disabled'}

Nhớ thay đổi IP address bằng tham số --ip nếu cần!
Ví dụ: python esp32_test.py --ip 192.168.1.100

""")
    
    esp32_detect()
