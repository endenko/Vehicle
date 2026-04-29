"""
Fuzzy matching logic cho xác thực biển số xe
Sử dụng thefuzz library để so khớp chuỗi OCR với danh sách biển số đã đăng ký
"""
import re
from typing import Tuple, List, Dict
from thefuzz import fuzz, process
from smart_parking.database import db_manager
from smart_parking.config import FUZZY_THRESHOLD, MIN_BALANCE_REQUIRED

def clean_extracted_text(raw_text: str) -> str:
    """
    Loại bỏ ký tự rác từ OCR
    Input: "43 A 1 - 1 2 3 4 5" hoặc "[43]A[1]-[12345]"
    Output: "43A1-12345"
    """
    # Loại bỏ các ký tự không phải chữ, số, gạch ngang
    cleaned = re.sub(r'[^\w\-]', '', raw_text.upper())
    # Chuẩn hóa định dạng: ABC123-456 -> ABC-123456 (nếu cần)
    cleaned = re.sub(r'\s+', '', cleaned)
    return cleaned.strip()

def fuzzy_match_plate(raw_ocr: str, ma_sv: str) -> Tuple[bool, str, str, int]:
    """
    So khớp mờ chuỗi OCR thô với danh sách biển số của sinh viên.
    
    Return:
        (Hợp lệ, Thông báo, Biển số khớp nhất, Độ tự tin %)
    """
    cleaned_text = clean_extracted_text(raw_ocr)
    
    # Lấy danh sách xe của sinh viên
    vehicles = db_manager.get_student_vehicles(ma_sv)
    
    if not vehicles:
        return False, f"[✗] Sinh viên {ma_sv} chưa đăng ký xe nào!", cleaned_text, 0
    
    valid_plates = [v['bien_so'] for v in vehicles]
    plate_status = {v['bien_so']: v['tinh_trang'] for v in vehicles}
    
    # So khớp bằng fuzzy matching
    best_match, confidence = process.extractOne(cleaned_text, valid_plates, scorer=fuzz.partial_ratio)
    
    # Kiểm tra ngưỡng tự tin
    if confidence >= FUZZY_THRESHOLD:
        status = plate_status.get(best_match, "Không rõ")
        
        if status == "Khóa":
            return False, f"[🔒] XE BỊ KHÓA: {best_match}", best_match, confidence
        
        return True, f"[✓] CHẤP NHẬN ({confidence}%): {best_match}", best_match, confidence
    
    # Nếu không khớp, trả về thông báo từ chối
    return False, f"[✗] KHÔNG KHỚP BIỂN SỐ (Độ tin cây: {confidence}% < {FUZZY_THRESHOLD}%)", cleaned_text, confidence

def authenticate_with_ocr(ma_sv: str, raw_ocr_text: str, check_balance: bool = True) -> Dict:
    """
    Xác thực toàn bộ: Lấy OCR, so khớp biển số, kiểm tra RFID, ghi log
    
    Return: Dict với các thông tin chi tiết
    """
    valid, message, plate, confidence = fuzzy_match_plate(raw_ocr_text, ma_sv)

    student = db_manager.get_student_by_id(ma_sv)
    rfid = db_manager.get_rfid_by_student(ma_sv)

    if student is None:
        valid = False
        message = f"[✗] Sinh viên {ma_sv} chưa tạo hồ sơ trong hệ thống!"

    if rfid is None:
        valid = False
        message = f"[✗] Sinh viên {ma_sv} chưa tạo tài khoản RFID!"
    else:
        rfid_status = str(rfid.get('tinh_trang', '')).strip()
        rfid_balance = int(rfid.get('so_du', 0) or 0)

        if rfid_status == "Khóa":
            valid = False
            message = f"[🔒] Thẻ RFID {rfid['ma_rfid']} đang bị khóa!"
        elif check_balance and rfid_balance < MIN_BALANCE_REQUIRED:
            valid = False
            message = (
                f"[✗] Không đủ tiền: số dư {rfid_balance} < {MIN_BALANCE_REQUIRED}."
            )

    return {
        'valid': valid,
        'message': message,
        'plate': plate,
        'confidence': confidence,
        'student': student,
        'rfid': rfid,
        'raw_ocr': raw_ocr_text,
        'cleaned_ocr': clean_extracted_text(raw_ocr_text),
    }

def batch_fuzzy_match(plate_list: List[str], reference_plates: List[str]) -> Dict[str, Tuple[str, int]]:
    """
    So khớp hàng loạt (hữu ích cho thống kê)
    """
    results = {}
    for plate in plate_list:
        best_match, confidence = process.extractOne(plate, reference_plates, scorer=fuzz.partial_ratio)
        results[plate] = (best_match, confidence)
    return results
