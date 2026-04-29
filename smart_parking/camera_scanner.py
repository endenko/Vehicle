"""
Camera Scanner Module - Quét QR/Barcode từ camera laptop
Sử dụng zxingcpp, cv2.QRCodeDetector, cv2.barcode_BarcodeDetector
"""
import cv2
import importlib
from typing import Optional, Tuple
from pathlib import Path

class CameraScanner:
    """Quét mã QR/Barcode từ webcam laptop"""
    
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap = cv2.VideoCapture(camera_index)
        self.qr_detector = cv2.QRCodeDetector()
        self.barcode_detector = None
        self.zxingcpp = None
        
        # Khởi tạo barcode detector
        if hasattr(cv2, "barcode_BarcodeDetector"):
            self.barcode_detector = cv2.barcode_BarcodeDetector()
        
        # Khởi tạo zxingcpp nếu có
        try:
            self.zxingcpp = importlib.import_module("zxingcpp")
            print("[✓] zxingcpp đã sẵn sàng")
        except ModuleNotFoundError:
            print("[⚠] zxingcpp không cài đặt. Sẽ dùng fallback methods.")
        
        if not self.cap.isOpened():
            raise RuntimeError("Không thể mở camera!")
    
    def read_frame(self) -> Tuple[bool, any]:
        """Đọc frame từ camera"""
        return self.cap.read()
    
    def detect_qr(self, frame) -> Optional[str]:
        """Quét mã QR"""
        try:
            decoded_text, _, _ = self.qr_detector.detectAndDecode(frame)
            if decoded_text and decoded_text.strip():
                return decoded_text.strip()
        except Exception as e:
            print(f"[✗] Lỗi quét QR: {e}")
        return None
    
    def detect_barcode_zxingcpp(self, frame) -> Optional[Tuple[str, str]]:
        """Quét barcode bằng zxingcpp"""
        if self.zxingcpp is None:
            return None
        
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            results = self.zxingcpp.read_barcodes(gray)
            
            for result in results:
                text = str(getattr(result, "text", "")).strip()
                if not text:
                    continue
                code_format = str(getattr(result, "format", "BARCODE")).strip() or "BARCODE"
                return text, code_format
        except Exception as e:
            print(f"[✗] Lỗi zxingcpp: {e}")
        return None
    
    def detect_barcode_opencv(self, frame) -> Optional[Tuple[str, str]]:
        """Quét barcode bằng OpenCV"""
        if self.barcode_detector is None:
            return None
        
        try:
            ok, decoded_infos, decoded_types, _ = self.barcode_detector.detectAndDecodeWithType(frame)
            
            if not ok:
                return None
            
            for idx, info in enumerate(decoded_infos):
                text = str(info).strip()
                if not text:
                    continue
                
                code_type = "BARCODE"
                if idx < len(decoded_types):
                    dt = str(decoded_types[idx]).strip()
                    if dt:
                        code_type = dt
                
                return text, code_type
        except Exception as e:
            print(f"[✗] Lỗi OpenCV barcode: {e}")
        return None
    
    def detect_any_code(self, frame) -> Optional[Tuple[str, str]]:
        """
        Quét mã (QR hoặc Barcode) từ frame
        Thứ tự ưu tiên: QR -> zxingcpp -> OpenCV
        
        Return: (code_text, code_type)
        """
        # Thử QR trước
        qr_text = self.detect_qr(frame)
        if qr_text:
            return qr_text, "QR"
        
        # Thử zxingcpp
        result = self.detect_barcode_zxingcpp(frame)
        if result:
            return result
        
        # Thử OpenCV barcode
        result = self.detect_barcode_opencv(frame)
        if result:
            return result
        
        return None
    
    def release(self):
        """Giải phóng camera"""
        if self.cap.isOpened():
            self.cap.release()
    
    def __del__(self):
        """Cleanup khi đối tượng bị hủy"""
        self.release()
