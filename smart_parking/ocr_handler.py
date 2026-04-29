"""
Roboflow + Google Vision + Tesseract OCR Handler
Dùng Roboflow để phát hiện vùng biển số, sau đó ưu tiên Google Cloud Vision, fallback về Tesseract.
"""
import base64
import os
import re
from typing import Optional, Dict, Any

import cv2
import numpy as np
import pytesseract
import requests
from google.cloud import vision

from smart_parking.config import ROBOFLOW_API_KEY, ROBOFLOW_URL


class LicensePlateOCR:
    """License plate OCR bằng Roboflow detection, Google Cloud Vision và Tesseract."""

    def __init__(self):
        self.google_client = None
        self._initialize_google_client()

    def _initialize_google_client(self):
        try:
            self.google_client = vision.ImageAnnotatorClient()
            print("[✓] Google Cloud Vision client initialized.")
        except Exception as e:
            print(f"[⚠️] Không thể khởi tạo Google Cloud Vision client: {e}")
            self.google_client = None

    def _normalize_text(self, raw_text: str) -> str:
        if not raw_text:
            return ""
        cleaned = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
        return cleaned.strip()

    def _detect_plate(self, image_array) -> Optional[np.ndarray]:
        if not ROBOFLOW_API_KEY or not ROBOFLOW_URL:
            print("[✗] ROBOFLOW API chưa được cấu hình.")
            return None

        try:
            success, buffer = cv2.imencode('.jpg', image_array, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not success:
                return None

            img_b64 = base64.b64encode(buffer).decode('ascii')
            response = requests.post(
                ROBOFLOW_URL,
                data=img_b64,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=5.0,
            )
            if response.status_code != 200:
                print(f"[✗] Roboflow response status: {response.status_code}")
                return None

            payload = response.json()
            predictions = payload.get('predictions', [])
            if not predictions:
                print("[⚠️] Roboflow không phát hiện được biển số.")
                return None

            best = max(predictions, key=lambda p: float(p.get('confidence', 0)))
            x = float(best.get('x', 0))
            y = float(best.get('y', 0))
            width = float(best.get('width', 0))
            height = float(best.get('height', 0))

            x1 = max(int(x - width / 2), 0)
            y1 = max(int(y - height / 2), 0)
            x2 = min(int(x + width / 2), image_array.shape[1])
            y2 = min(int(y + height / 2), image_array.shape[0])

            if x2 <= x1 or y2 <= y1:
                print("[⚠️] Roboflow trả về bounding box không hợp lệ.")
                return None

            plate_crop = image_array[y1:y2, x1:x2]
            if plate_crop.size == 0:
                print("[⚠️] Khu vực cắt biển số rỗng.")
                return None

            return plate_crop
        except Exception as e:
            print(f"[✗] Lỗi Roboflow detection: {e}")
            return None

    def _read_with_google(self, image_array) -> Optional[str]:
        if self.google_client is None:
            return None

        try:
            success, buffer = cv2.imencode('.jpg', image_array, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not success:
                return None

            gcv_image = vision.Image(content=buffer.tobytes())
            response = self.google_client.text_detection(image=gcv_image, timeout=5.0)
            if getattr(response, 'error', None) and response.error.message:
                print(f"[✗] Google Vision error: {response.error.message}")
                return None

            annotations = getattr(response, 'text_annotations', [])
            if not annotations:
                return None

            raw = annotations[0].description.strip()
            cleaned = self._normalize_text(raw)
            return cleaned or None
        except Exception as e:
            print(f"[✗] Google Vision OCR failed: {e}")
            return None

    def _read_with_tesseract(self, image_array) -> Optional[str]:
        try:
            image = cv2.resize(image_array, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')
            config = r"--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

            raw = pytesseract.image_to_string(thresh, config=config).strip()
            cleaned = self._normalize_text(raw)
            if cleaned:
                return cleaned

            raw = pytesseract.image_to_string(gray, config=config).strip()
            cleaned = self._normalize_text(raw)
            return cleaned or None
        except Exception as e:
            print(f"[✗] Tesseract OCR failed: {e}")
            return None

    def extract_text(self, image_array) -> Dict[str, Any]:
        result = {
            'plate_crop': None,
            'google_text': None,
            'tesseract_text': None,
            'text': None,
            'source': 'none',
            'error': None,
        }

        plate_crop = self._detect_plate(image_array)
        result['plate_crop'] = plate_crop
        if plate_crop is None:
            result['error'] = 'Roboflow không phát hiện biển số.'
            return result

        google_text = self._read_with_google(plate_crop)
        result['google_text'] = google_text
        if google_text:
            result['text'] = google_text
            result['source'] = 'google'
            return result

        tesseract_text = self._read_with_tesseract(plate_crop)
        result['tesseract_text'] = tesseract_text
        if tesseract_text:
            result['text'] = tesseract_text
            result['source'] = 'tesseract'
            return result

        result['error'] = 'OCR failed with both Google Vision and Tesseract.'
        return result

    def extract_license_plate_text(self, image_array) -> Optional[str]:
        return self.extract_text(image_array).get('text')
