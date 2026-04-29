"""
Google Cloud Vision Handler
Xử lý OCR bằng Google Cloud Vision API
"""
from google.cloud import vision
from typing import Optional
import os

class GoogleVisionOCR:
    """Xử lý OCR bằng Google Cloud Vision"""
    
    def __init__(self):
        try:
            self.client = vision.ImageAnnotatorClient()
            print("[✓] Google Cloud Vision client khởi tạo thành công")
        except Exception as e:
            print(f"[✗] Lỗi khởi tạo Vision client: {e}")
            self.client = None
    
    def extract_text(self, image_array) -> Optional[str]:
        """
        Trích xuất text từ image
        
        Args:
            image_array: numpy array (từ cv2.imread)
        
        Returns:
            Chuỗi text trích xuất, hoặc None nếu có lỗi
        """
        if self.client is None:
            return None
        
        try:
            # Chuyển numpy array thành bytes
            import cv2
            _, buffer = cv2.imencode('.jpg', image_array)
            
            image = vision.Image(content=buffer.tobytes())
            response = self.client.text_detection(image=image)
            
            if response.error.message:
                print(f"[✗] Vision API error: {response.error.message}")
                return None
            
            if response.text_annotations:
                # Lấy full text từ annotation đầu tiên (full page)
                return response.text_annotations[0].description.strip()
            
            return None
        
        except Exception as e:
            print(f"[✗] Lỗi trích xuất text: {e}")
            return None
    
    def extract_license_plate_text(self, image_array) -> Optional[str]:
        """
        Trích xuất text từ biển số (tối ưu cho loại ảnh này)
        """
        return self.extract_text(image_array)
