"""
gui/utils/db_local.py
Wrapper nhỏ dùng smart_parking.database.db_manager + tính phí xe ra.
"""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import glob

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
SURCHARGE_24H = 5000  # Phụ phí nếu gửi quá 24 giờ


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


def calc_fee_with_surcharge(time_in_str: str, time_out: datetime = None) -> dict:
    """
    Tính phí có tính phụ phí 5,000đ nếu gửi quá 24 giờ.

    Returns:
        dict: {"base_fee": int, "surcharge": int, "total": int, "hours_parked": float, "rejected": bool}
    """
    now = time_out or datetime.now()
    base_fee = calc_fee(now)

    if base_fee == -1:
        return {"base_fee": 0, "surcharge": 0, "total": 0, "hours_parked": 0, "rejected": True}

    hours_parked = 0.0
    surcharge = 0
    if time_in_str:
        try:
            if isinstance(time_in_str, datetime):
                time_in = time_in_str
            else:
                time_in = datetime.fromisoformat(str(time_in_str))
            delta = now - time_in
            hours_parked = delta.total_seconds() / 3600.0
            if hours_parked >= 24.0:
                surcharge = SURCHARGE_24H
        except (ValueError, TypeError):
            pass

    total = base_fee + surcharge
    return {
        "base_fee": base_fee,
        "surcharge": surcharge,
        "total": total,
        "hours_parked": round(hours_parked, 1),
        "rejected": False,
        "time_in_str": time_in_str,
    }


def is_operating_hours(now: datetime = None) -> bool:
    return calc_fee(now) != -1


# ── Lookup sinh viên ──────────────────────────────────────────────────────────
def lookup_by_barcode(barcode: str) -> dict:
    """
    Tìm sinh viên qua RFID, QR (JSON payload) hoặc Barcode (EAN-13).
    """
    if not barcode:
        return None
        
    # Xử lý nếu là mã QR (chứa JSON payload)
    if "MSSV" in barcode:
        try:
            import json
            data = json.loads(barcode)
            barcode = data.get("MSSV", barcode)
        except Exception:
            pass

    db_manager.connect()

    # Xử lý nếu là mã Barcode EAN-13 (13 số, bắt đầu bằng 893)
    if barcode.startswith("893") and len(barcode) == 13 and barcode.isdigit():
        import re, zlib
        def _build_ean13_check_digit(base12: str) -> str:
            odd_sum = sum(int(base12[i]) for i in range(0, 12, 2))
            even_sum = sum(int(base12[i]) for i in range(1, 12, 2))
            return str((10 - ((odd_sum + (3 * even_sum)) % 10)) % 10)

        # Lấy tất cả MaSV để đối chiếu hash
        students = db_manager.execute_query("SELECT MaSV FROM SinhVien")
        if students:
            for st in students:
                masv = st['MaSV']
                normalized = re.sub(r"[^A-Z0-9]", "", masv.upper()) or "UNKNOWN"
                hash_suffix = zlib.crc32(normalized.encode("utf-8")) % 1_000_000_000
                base12 = f"893{hash_suffix:09d}"
                expected = f"{base12}{_build_ean13_check_digit(base12)}"
                if expected == barcode:
                    barcode = masv
                    break

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


# ── Tìm ảnh xe vào theo biển số ──────────────────────────────────────────────
def find_entry_image(bien_so: str) -> str:
    """
    Tìm ảnh xe vào theo biển số trong thư mục Lich su bien so xe/xe_vao.
    Trả về đường dẫn file ảnh hoặc chuỗi rỗng nếu không tìm thấy.
    """
    if not bien_so:
        return ""
    search_dirs = [
        _BASE / "Lich su bien so xe" / "xe_vao",
        _BASE / "static" / "in",
    ]
    safe_plate = bien_so.replace("-", "").replace(" ", "")
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        # Tìm theo pattern: *BienSo*.jpg
        for ext in ["*.jpg", "*.png", "*.jpeg"]:
            for fp in sorted(search_dir.glob(ext), key=lambda f: f.stat().st_mtime, reverse=True):
                if safe_plate in fp.name.replace("-", "").replace(" ", ""):
                    return str(fp)
        # Fallback: lấy file mới nhất
        all_imgs = sorted(search_dir.glob("*.jpg"), key=lambda f: f.stat().st_mtime, reverse=True)
        if all_imgs:
            return str(all_imgs[0])
    return ""


# ── Lấy thời gian vào của xe đang đỗ ─────────────────────────────────────────
def get_entry_time_for_plate(bien_so: str) -> str:
    """Trả về chuỗi ThoiGianVao nếu xe đang đỗ, hoặc '' nếu không tìm thấy."""
    if not bien_so:
        return ""
    db_manager.connect()
    entry = db_manager.get_active_entry_by_plate(bien_so)
    if entry:
        return str(entry.get("thoi_gian_vao", ""))
    return ""


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
    5. Kiểm tra số dư (có phụ phí 24h)
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
                "rescan": True,
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

    # 5. Kiểm tra số dư (kèm phụ phí 24h)
    time_in_str = get_entry_time_for_plate(matched_plate)
    fee_info = calc_fee_with_surcharge(time_in_str, now)
    total_fee = fee_info["total"]

    so_du = int(student_info.get("so_du", 0) or 0)
    if so_du < total_fee:
        surcharge_msg = ""
        if fee_info["surcharge"] > 0:
            surcharge_msg = f" (gồm phụ phí 24h: {fee_info['surcharge']:,}đ)"
        return {
            "ok": False,
            "insufficient": True,
            "message": (f"⚠ Không đủ tiền! Số dư: {so_du:,}đ | "
                        f"Phí: {total_fee:,}đ{surcharge_msg}"),
            "student": student_info,
            "fee": total_fee,
            "fee_info": fee_info,
        }

    # 6. Ghi log + trừ tiền
    ma_rfid = student_info.get("ma_rfid", barcode)
    ok_log = db_manager.add_exit_log(matched_plate, anh_path, total_fee)
    ok_bal = db_manager.update_rfid_balance(ma_rfid, -total_fee)

    surcharge_msg = ""
    if fee_info["surcharge"] > 0:
        surcharge_msg = f" (gồm phụ phí 24h: {fee_info['surcharge']:,}đ)"

    return {
        "ok": ok_log and ok_bal,
        "message": (f"✔ Xe ra thành công. Trừ {total_fee:,}đ{surcharge_msg}. "
                    f"Còn lại: {so_du - total_fee:,}đ"),
        "student": student_info,
        "fee": total_fee,
        "fee_info": fee_info,
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
