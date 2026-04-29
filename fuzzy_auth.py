import re
from thefuzz import fuzz, process
from database import get_student_vehicles

def clean_extracted_text(raw_text: str) -> str:
    """Loại bỏ ký tự rác từ OCR"""
    lines = raw_text.strip().split('\n')
    cleaned_lines = [re.sub(r'[^A-Z0-9]', '', line.upper()) for line in lines if len(re.sub(r'[^A-Z0-9]', '', line.upper())) >= 3]
    if len(cleaned_lines) >= 2:
        return f"{cleaned_lines[0]}-{cleaned_lines[1]}"
    elif len(cleaned_lines) == 1:
        return cleaned_lines[0]
    return raw_text

def authenticate_vehicle(ma_sv: str, raw_ocr_text: str) -> tuple[bool, str, str]:
    """
    So khớp chuỗi OCR thô với danh sách biển số hợp lệ của sinh viên.
    Trả về: (Hợp lệ hay không, Thông báo, Biển số khớp nhất)
    """
    cleaned_text = clean_extracted_text(raw_ocr_text)
    records = get_student_vehicles(ma_sv)
    
    if not records:
        return False, f"LỖI: Sinh viên {ma_sv} chưa đăng ký xe!", cleaned_text

    valid_plates = [r[0] for r in records]
    
    # So khớp mờ
    best_match, confidence = process.extractOne(cleaned_text, valid_plates, scorer=fuzz.partial_ratio)

    if confidence >= 75: # Ngưỡng tự tin 75%
        status = next(r[1] for r in records if r[0] == best_match)
        if status == "Khóa":
            return False, f"CẢNH BÁO: Xe {best_match} đang bị KHÓA!", best_match
        return True, f"CHẤP NHẬN ({confidence}%): {best_match}", best_match
    
    return False, f"TỪ CHỐI: Không khớp biển số (Độ tự tin: {confidence}%)", cleaned_text