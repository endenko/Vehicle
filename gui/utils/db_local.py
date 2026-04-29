"""
gui/utils/db_local.py
Wrapper nhỏ dùng smart_parking.database.db_manager + tính phí xe ra.
"""
from datetime import datetime
from pathlib import Path
import sys

# Đảm bảo import được smart_parking
_BASE = Path(__file__).resolve().parents[2]
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

from smart_parking.database import db_manager  # noqa: E402
from smart_parking.config import FUZZY_THRESHOLD  # noqa: E402

try:
    from thefuzz import fuzz, process as fuzz_process
    _HAS_FUZZ = True
except Exception:
    _HAS_FUZZ = False


# ── Phí gửi xe ────────────────────────────────────────────────────────────────
def calc_fee(time_out: datetime = None) -> int:
    """
    6:00 – 17:30  → 2,000đ
    17:30 – 23:00 → 3,000đ
    23:00 – 6:00  → từ chối (return -1)
    """
    now = time_out or datetime.now()
    h = now.hour + now.minute / 60.0
    if 6.0 <= h < 17.5:
        return 2000
    if 17.5 <= h < 23.0:
        return 3000
    return -1  # ngoài giờ hoạt động


def is_operating_hours(now: datetime = None) -> bool:
    return calc_fee(now) != -1


# ── Lookup sinh viên ──────────────────────────────────────────────────────────
def lookup_by_barcode(barcode: str) -> dict:
    """
    Tìm sinh viên qua RFID (MaRFID = barcode hoặc MaSV = barcode).
    Trả về dict: ho_ten, khoa, lop, sdt, so_du, tinh_trang, ma_rfid, ma_sv, vehicles[]
    hoặc None nếu không tìm thấy.
    """
    if not barcode:
        return None
    db_manager.connect()

    # Thử tìm theo RFID
    info = db_manager.get_student_by_rfid(barcode)
    rfid_code = barcode
    if info is None:
        # Thử tìm theo MaSV
        student = db_manager.get_student_by_id(barcode)
        if student is None:
            return None
        rfid = db_manager.get_rfid_by_student(barcode)
        if rfid:
            info = {
                'ma_sv': student['ma_sv'],
                'ho_ten': student['ho_ten'],
                'khoa': student['khoa'],
                'lop': student['lop'],
                'sdt': student['sdt'],
                'so_du': rfid['so_du'],
                'tinh_trang': rfid['tinh_trang'],
            }
            rfid_code = rfid['ma_rfid']
        else:
            return None

    info['ma_rfid'] = rfid_code
    info['vehicles'] = db_manager.get_student_vehicles(info.get('ma_sv', ''))
    return info


# ── Xe vào ────────────────────────────────────────────────────────────────────
def process_entry(barcode: str, bien_so: str, anh_path: str = "") -> dict:
    """
    Ghi log vào xe. Trả về dict kết quả.
    """
    db_manager.connect()
    student_info = lookup_by_barcode(barcode)
    if student_info is None:
        return {"ok": False, "message": "Không tìm thấy sinh viên trong hệ thống."}

    if str(student_info.get("tinh_trang", "")).strip() == "Khóa":
        return {"ok": False, "message": "⛔ Thẻ RFID bị khóa!", "student": student_info}

    ma_rfid = student_info.get("ma_rfid", barcode)
    ok = db_manager.add_entry_log(ma_rfid, bien_so, anh_path)
    if ok:
        return {"ok": True, "message": "✔ Xe vào thành công.", "student": student_info}
    return {"ok": False, "message": "Lỗi ghi log vào DB.", "student": student_info}


# ── Xe ra ─────────────────────────────────────────────────────────────────────
def process_exit(barcode: str, bien_so_quet: str, anh_path: str = "") -> dict:
    """
    Xử lý xe ra:
    1. Kiểm tra giờ hoạt động
    2. Tra DB theo barcode
    3. Fuzzy match biển số
    4. Kiểm tra khóa xe
    5. Kiểm tra số dư
    6. Trừ tiền + ghi log
    """
    db_manager.connect()
    now = datetime.now()

    # 1. Giờ hoạt động
    fee = calc_fee(now)
    if fee == -1:
        return {
            "ok": False,
            "message": "⛔ Ngoài giờ hoạt động (23:00 – 06:00). Không nhận xe ra!",
            "alert": True,
        }

    # 2. Tra DB
    student_info = lookup_by_barcode(barcode)
    if student_info is None:
        return {"ok": False, "message": "Không tìm thấy sinh viên trong hệ thống."}

    # 3. Fuzzy match biển số
    vehicles = student_info.get("vehicles", [])
    plate_match_score = 0
    matched_plate = bien_so_quet
    if vehicles and bien_so_quet and _HAS_FUZZ:
        plates = [v["bien_so"] for v in vehicles]
        best, score = fuzz_process.extractOne(
            bien_so_quet.upper(), plates, scorer=fuzz.partial_ratio
        )
        plate_match_score = score
        matched_plate = best
        if score < FUZZY_THRESHOLD:
            return {
                "ok": False,
                "message": (f"⚠ Biển số không khớp! Quét: {bien_so_quet} | "
                            f"Khớp gần nhất: {best} ({score}%)"),
                "student": student_info,
                "plate_score": score,
            }

    # 4. Khóa xe
    locked = str(student_info.get("tinh_trang", "")).strip() == "Khóa"
    if locked:
        return {
            "ok": False,
            "locked": True,
            "message": f"⛔ XE BỊ KHÓA! Chủ xe: {student_info.get('ho_ten')}",
            "student": student_info,
        }

    # 5. Kiểm tra số dư
    so_du = int(student_info.get("so_du", 0) or 0)
    if so_du < fee:
        return {
            "ok": False,
            "insufficient": True,
            "message": (f"⚠ Không đủ tiền! Số dư: {so_du:,}đ | "
                        f"Phí: {fee:,}đ"),
            "student": student_info,
            "fee": fee,
        }

    # 6. Ghi log + trừ tiền
    ma_rfid = student_info.get("ma_rfid", barcode)
    ok_log = db_manager.add_exit_log(matched_plate, anh_path, fee)
    ok_bal = db_manager.update_rfid_balance(ma_rfid, -fee)

    return {
        "ok": ok_log and ok_bal,
        "message": (f"✔ Xe ra thành công. Trừ {fee:,}đ. "
                    f"Còn lại: {so_du - fee:,}đ"),
        "student": student_info,
        "fee": fee,
        "plate_score": plate_match_score,
        "matched_plate": matched_plate,
    }


# ── History ───────────────────────────────────────────────────────────────────
def get_history(limit: int = 200):
    db_manager.connect()
    return db_manager.get_parking_history(limit)


def get_active(limit: int = 200):
    db_manager.connect()
    return db_manager.get_active_transactions(limit)


def get_stats():
    db_manager.connect()
    return db_manager.get_statistics()
