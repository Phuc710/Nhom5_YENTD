import os
import cv2
import numpy as np
import logging
from rapidocr_onnxruntime import RapidOCR

logger = logging.getLogger(__name__)

class LicensePlateOCR:
    """
    OCR Module using RapidOCR (ONNX Runtime based).
    Loads models from the backend/ocr directory.
    """
    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu
        
        # Paths to ONNX models
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.det_model_path = os.path.join(base_path, "ocr", "ch_PP-OCRv4_det_infer.onnx")
        self.rec_model_path = os.path.join(base_path, "ocr", "ch_PP-OCRv4_rec_infer.onnx")
        self.keys_path = os.path.join(base_path, "ocr", "ppocr_keys_v1.txt")
        
        # Check if models exist
        if not os.path.exists(self.det_model_path) or not os.path.exists(self.rec_model_path):
            logger.warning(f"OCR Models not found at {self.det_model_path} or {self.rec_model_path}. Falling back to default RapidOCR models.")
            self.engine = RapidOCR(use_cuda=use_gpu)
        else:
            logger.info(f"Loading custom OCR models: {self.det_model_path}, {self.rec_model_path}")
            self.engine = RapidOCR(
                det_model_path=self.det_model_path,
                rec_model_path=self.rec_model_path,
                rec_keys_path=self.keys_path,
                use_cuda=use_gpu
            )

    def __call__(self, image: np.ndarray):
        """
        Perform OCR on a single image (e.g., license plate crop).
        Returns: (text, confidence)
        """
        if image is None or image.size == 0:
            return "", 0.0

        try:
            # RapidOCR returns: [ [ [bbox], text, score ], ... ], latency
            results, _ = self.engine(image)
            
            if not results:
                return "", 0.0

            # For license plates, we usually expect a single result or we combine them
            # Sorting by confidence if multiple are found, or just take the best one.
            # Here we take the longest text string as primary for license plates (often 2 lines are combined)
            
            texts = [r[1] for r in results]
            scores = [r[2] for r in results]
            
            # Combine multiple lines if present (common for stacked VN plates)
            combined_text = "".join(texts).replace(" ", "").upper()
            avg_score = sum(scores) / len(scores) if scores else 0.0
            
            return combined_text, avg_score
            
        except Exception as e:
            logger.error(f"OCR inference failed: {e}")
            return "", 0.0

class DummyOCR:
    """Fallback dummy model for testing."""
    def __init__(self):
        print("Using dummy OCR model!")

    def __call__(self, image):
        return "30A12345", 0.99
