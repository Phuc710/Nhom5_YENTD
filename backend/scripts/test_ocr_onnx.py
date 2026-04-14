"""
Quick smoke test for the ONNX plate OCR pipeline.
Usage: python scripts/test_ocr_onnx.py [image_path]
"""
import sys
import os
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from utils.license_plate_ocr import LicensePlateOCR


def test_ocr_engine():
    print("=== OCR Engine Test ===")
    ocr = LicensePlateOCR(use_gpu=False)
    print("  [OK] Engine initialized")

    # Synthetic plate image
    img = np.ones((64, 200, 3), dtype=np.uint8) * 255
    cv2.putText(img, "51G1-65432", (8, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    text, conf = ocr(img)
    print(f"  [OK] OCR result: '{text}'  conf={conf:.2f}")


def test_full_pipeline(image_path: str = None):
    from utils.alpr_core import ALPRCore
    import glob

    plate_weight = None
    for pattern in [
        os.path.join(ROOT, "models", "*.pt"),
        os.path.join(ROOT, "weights", "*.pt"),
        os.path.join(ROOT, "*.pt"),
    ]:
        hits = glob.glob(pattern)
        if hits:
            plate_weight = hits[0]
            break

    if plate_weight is None:
        print("  [SKIP] No .pt model found. Skipping full pipeline test.")
        return

    print(f"\n=== Full Pipeline Test ===")
    print(f"  Model : {plate_weight}")
    core = ALPRCore(plate_weight=plate_weight, device="cpu", pconf=0.25)
    print("  [OK] ALPRCore initialized")

    if image_path and os.path.exists(image_path):
        frame = cv2.imread(image_path)
    else:
        frame = np.ones((480, 640, 3), dtype=np.uint8) * 80  # grey blank

    annotated, results = core.process_frame(frame)
    print(f"  [OK] process_frame done — {len(results)} plate(s) found")
    for r in results:
        print(f"       bbox={r.bbox_xyxy}  text='{r.text}'  conf={r.conf:.2f}")


if __name__ == "__main__":
    img_arg = sys.argv[1] if len(sys.argv) > 1 else None
    test_ocr_engine()
    test_full_pipeline(img_arg)
