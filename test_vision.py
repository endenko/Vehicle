import os
import cv2
from smart_parking.ocr_handler import GoogleVisionOCR

print("Khởi tạo Google Vision...")
try:
    ocr = GoogleVisionOCR()
    print("✅ Khởi tạo thành công")
except Exception as e:
    print(f"❌ Lỗi khởi tạo: {e}")
    exit(1)

img_path = "/home/minhviet/Documents/TestThuGui/Lich_su_xe_vao/73M1-88912_20260503_080358.jpg"
print(f"Đọc file: {img_path}")
frame = cv2.imread(img_path)

if frame is None:
    print("❌ Không đọc được ảnh")
    exit(1)

print("Đang gửi yêu cầu OCR...")
try:
    text = ocr.extract_text(frame)
    print(f"✅ Kết quả OCR:\n{text}")
except Exception as e:
    print(f"❌ Lỗi khi gửi OCR: {e}")
