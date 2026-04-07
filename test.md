# Webcam USB / laptop mặc định:
python test_detect_ocr.py

# Stream MJPEG từ ESP32:
python test_detect_ocr.py --source http://192.168.1.226:81/stream

# File video:
python test_detect_ocr.py --source test2.mp4

# Chỉ detect (tắt OCR, nhanh hơn):
python test_detect_ocr.py --no-ocr

# Tắt filter Zone (detect toàn frame):
python test_detect_ocr.py --no-zone


python test_lp_line.py test2.mp4