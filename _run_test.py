import sys
sys.path.insert(0, 'backend')

import cv2
from backend.ml.detector import get_detector

det = get_detector()
result = det.detect_and_read_plate(cv2.imread(r'test.png'))
print('success:', result['success'])
for p in result['plates']:
    print(f'  bbox={p["bbox"]}  text="{p["text"]}"  conf={p["confidence"]:.2f}  small={p["is_small"]}')
if not result['plates']:
    print('  error:', result['error'])
