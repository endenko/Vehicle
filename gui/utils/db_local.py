"""
gui/utils/db_local.py
Wrapper nhỏ dùng smart_parking.database.db_manager + tính phí xe ra.
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import csv
import glob
import shutil
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


SECURITY_AUDIT_LOG = _BASE / "security_audit.log"
DB_BACKUP_DIR = _BASE / "db_backup"


def _format_dt(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    try:
        return datetime.fromisoformat(str(value)).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(value)


def append_security_audit(action: str, subject: str, status: str, details: str = "") -> None:
    """Ghi nhật ký kiểm toán cục bộ cho các hành vi nhạy cảm."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] - {action} - {subject} - {status}"
    if details:
        line = f"{line} - {details}"
    try:
        SECURITY_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SECURITY_AUDIT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def backup_primary_database() -> Optional[str]:
    """Sao lưu file SQLite chính và chỉ giữ lại 7 bản gần nhất."""
    source_path = Path(getattr(db_manager, "sqlite_path", _BASE / "smart_parking.db"))
    if not source_path.exists():
        legacy_path = _BASE / "database.db"
        if legacy_path.exists():
            source_path = legacy_path
        else:
            return None

    DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_name = f"database_backup_{datetime.now().strftime('%Y%m%d')}.db"
    backup_path = DB_BACKUP_DIR / backup_name
    try:
        shutil.copy2(source_path, backup_path)

        backups = sorted(
            DB_BACKUP_DIR.glob("database_backup_*.db"),
            key=lambda file_path: file_path.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[7:]:
            try:
                old_backup.unlink()
            except Exception:
                pass
        return str(backup_path)
    except Exception:
        return None


def search_active_transactions(keyword: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Tìm xe đang đỗ theo biển số, MSSV hoặc tên chủ xe."""
    keyword = (keyword or "").strip()
    if not keyword:
        return get_active(limit=limit)

    db_manager.connect()
    like_value = f"%{keyword}%"
    if db_manager.engine == "sqlserver":
        query = (
            "SELECT TOP (?) lsr.ID, lsr.BienSo, lsr.ThoiGianVao, lsr.TrangThai, "
            "sv.HoTen, sv.MaSV, sv.Lop, sv.Khoa "
            "FROM LichSuVaoRa lsr "
            "JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID "
            "JOIN SinhVien sv ON rfid.MaSV = sv.MaSV "
            "WHERE lsr.TrangThai = 'Đang đỗ' AND (lsr.BienSo LIKE ? OR sv.MaSV LIKE ? OR sv.HoTen LIKE ?) "
            "ORDER BY lsr.ThoiGianVao DESC"
        )
        params = (limit, like_value, like_value, like_value)
    else:
        query = (
            "SELECT lsr.ID, lsr.BienSo, lsr.ThoiGianVao, lsr.TrangThai, "
            "sv.HoTen, sv.MaSV, sv.Lop, sv.Khoa "
            "FROM LichSuVaoRa lsr "
            "JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID "
            "JOIN SinhVien sv ON rfid.MaSV = sv.MaSV "
            "WHERE lsr.TrangThai = 'Đang đỗ' AND (lsr.BienSo LIKE ? OR sv.MaSV LIKE ? OR sv.HoTen LIKE ?) "
            "ORDER BY lsr.ThoiGianVao DESC "
            "LIMIT ?"
        )
        params = (like_value, like_value, like_value, limit)

    rows = db_manager.execute_query(query, params)
    active = []
    for row in rows:
        active.append(
            {
                'transaction_id': row.get('ID', row.get('transaction_id', '-')),
                'license_plate': row.get('BienSo', row.get('license_plate', '-')),
                'time_in': row.get('ThoiGianVao', row.get('time_in')),
                'status': row.get('TrangThai', row.get('status', '-')),
                'owner_name': row.get('HoTen', row.get('owner_name', '-')),
                'owner_identity': row.get('MaSV', row.get('owner_identity', '-')),
                'owner_class': row.get('Lop', row.get('owner_class', '-')),
                'owner_major': row.get('Khoa', row.get('owner_major', '-')),
            }
        )
    return active


def get_monthly_history(year: Optional[int] = None, month: Optional[int] = None) -> List[Dict[str, Any]]:
    """Lấy lịch sử vào/ra của tháng hiện tại để xuất báo cáo."""
    target = datetime.now()
    year = year or target.year
    month = month or target.month

    db_manager.connect()
    if db_manager.engine == "sqlserver":
        query = (
            "SELECT lsr.ID, lsr.BienSo, lsr.ThoiGianVao, lsr.ThoiGianRa, lsr.TrangThai, lsr.SoTienTru, "
            "sv.HoTen, sv.MaSV, sv.Lop, sv.Khoa, rfid.SoDu, rfid.TinhTrang "
            "FROM LichSuVaoRa lsr "
            "JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID "
            "JOIN SinhVien sv ON rfid.MaSV = sv.MaSV "
            "WHERE YEAR(COALESCE(lsr.ThoiGianRa, lsr.ThoiGianVao)) = ? "
            "  AND MONTH(COALESCE(lsr.ThoiGianRa, lsr.ThoiGianVao)) = ? "
            "ORDER BY lsr.ID DESC"
        )
        rows = db_manager.execute_query(query, (year, month))
    else:
        query = (
            "SELECT lsr.ID, lsr.BienSo, lsr.ThoiGianVao, lsr.ThoiGianRa, lsr.TrangThai, lsr.SoTienTru, "
            "sv.HoTen, sv.MaSV, sv.Lop, sv.Khoa, rfid.SoDu, rfid.TinhTrang "
            "FROM LichSuVaoRa lsr "
            "JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID "
            "JOIN SinhVien sv ON rfid.MaSV = sv.MaSV "
            "WHERE strftime('%Y-%m', COALESCE(lsr.ThoiGianRa, lsr.ThoiGianVao)) = ? "
            "ORDER BY lsr.ID DESC"
        )
        rows = db_manager.execute_query(query, (f"{year:04d}-{month:02d}",))

    history: List[Dict[str, Any]] = []
    for row in rows:
        history.append(
            {
                'transaction_id': row.get('ID', '-'),
                'license_plate': row.get('BienSo', '-'),
                'time_in': row.get('ThoiGianVao'),
                'time_out': row.get('ThoiGianRa'),
                'status': row.get('TrangThai', '-'),
                'fee': row.get('SoTienTru', 0) or 0,
                'owner_name': row.get('HoTen', '-'),
                'owner_identity': row.get('MaSV', '-'),
                'owner_class': row.get('Lop', '-'),
                'owner_major': row.get('Khoa', '-'),
                'owner_balance': row.get('SoDu', 0) or 0,
                'rfid_status': row.get('TinhTrang', '-'),
            }
        )
    return history


def export_monthly_history_csv(output_path: Optional[Path] = None) -> Optional[str]:
    """Xuất báo cáo CSV cho tháng hiện tại."""
    history = get_monthly_history()
    if not history:
        return None

    report_dir = _BASE / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    target = output_path or (report_dir / f"parking_report_{datetime.now().strftime('%Y%m')}.csv")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "transaction_id",
        "license_plate",
        "owner_identity",
        "owner_name",
        "owner_class",
        "owner_major",
        "time_in",
        "time_out",
        "status",
        "fee",
        "owner_balance",
        "rfid_status",
    ]

    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in history:
            writer.writerow(
                {
                    "transaction_id": item.get("transaction_id", ""),
                    "license_plate": item.get("license_plate", ""),
                    "owner_identity": item.get("owner_identity", ""),
                    "owner_name": item.get("owner_name", ""),
                    "owner_class": item.get("owner_class", ""),
                    "owner_major": item.get("owner_major", ""),
                    "time_in": _format_dt(item.get("time_in")),
                    "time_out": _format_dt(item.get("time_out")),
                    "status": item.get("status", ""),
                    "fee": int(item.get("fee") or 0),
                    "owner_balance": int(item.get("owner_balance") or 0),
                    "rfid_status": item.get("rfid_status", ""),
                }
            )

    return str(target)


# ── Lookup sinh viên ──────────────────────────────────────────────────────────
def lookup_by_barcode(barcode: str) -> dict:
    """
    Tìm sinh viên qua RFID, QR (JSON payload) hoặc Barcode (EAN-13).
    """
    if not barcode:
        return None
        
    qr_data = None
    # Xử lý nếu là mã QR (chứa JSON payload)
    if "MSSV" in barcode:
        try:
            import json
            qr_data = json.loads(barcode)
            barcode = qr_data.get("MSSV", barcode)
        except Exception:
            qr_data = None

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

    info = db_manager.get_student_by_rfid(barcode)
    rfid_code = barcode
    if info is None:
        # Thử tìm theo MaSV
        student = db_manager.get_student_by_id(barcode)
        if student is None:
            if qr_data is not None:
                # Trả về dữ liệu từ QR để hiển thị luôn
                return {
                    'ma_sv': qr_data.get("MSSV", barcode),
                    'ho_ten': qr_data.get("HoTen", "Không xác định"),
                    'khoa': qr_data.get("Khoa", ""),
                    'lop': qr_data.get("Lop", ""),
                    'sdt': qr_data.get("SDT", ""),
                    'so_du': 0,
                    'tinh_trang': "Bình thường",
                    'ma_rfid': barcode,
                    'vehicles': [{"bien_so": qr_data.get("BienSo", "")}] if qr_data.get("BienSo") else []
                }
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
            if qr_data is not None:
                return {
                    'ma_sv': qr_data.get("MSSV", barcode),
                    'ho_ten': qr_data.get("HoTen", "Không xác định"),
                    'khoa': qr_data.get("Khoa", ""),
                    'lop': qr_data.get("Lop", ""),
                    'sdt': qr_data.get("SDT", ""),
                    'so_du': 0,
                    'tinh_trang': "Bình thường",
                    'ma_rfid': barcode,
                    'vehicles': [{"bien_so": qr_data.get("BienSo", "")}] if qr_data.get("BienSo") else []
                }
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


def is_vehicle_in_lot(ma_rfid: str = None, bien_so: str = None) -> Optional[dict]:
    """
    Kiểm tra xem xe có đang trong bãi không.
    Trả về dict transaction nếu có, ngược lại None.
    """
    db_manager.connect()
    if bien_so:
        active = db_manager.get_active_entry_by_plate(bien_so)
        if active: return active
    
    if ma_rfid:
        # Tìm xem RFID này có transaction nào đang 'Đang đỗ' không
        # Cần thêm method vào db_manager hoặc viết query trực tiếp
        query = "SELECT ID, MaRFID, BienSo, ThoiGianVao FROM LichSuVaoRa WHERE MaRFID = ? AND TrangThai = 'Đang đỗ'"
        res = db_manager.execute_query(query, (ma_rfid,))
        if res: return res[0]
        
    return None



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
def process_exit(
    barcode: str,
    bien_so_quet: str,
    anh_path: str = "",
    force: bool = False,
    manual_note: str = "",
) -> dict:
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

    ma_rfid = student_info.get("ma_rfid", barcode)

    # 3. Fuzzy match biển số
    vehicles = student_info.get("vehicles", [])
    plate_match_score = 0
    matched_plate = (bien_so_quet or "").strip()
    if not matched_plate and vehicles:
        matched_plate = vehicles[0].get("bien_so", "")

    if vehicles and matched_plate and _HAS_FUZZ:
        plates = [v["bien_so"] for v in vehicles]
        best, score = fuzz_process.extractOne(
            bien_so_quet.upper(), plates, scorer=fuzz.partial_ratio
        )
        plate_match_score = score
        if best:
            matched_plate = best
        if (not force) and score < FUZZY_THRESHOLD:
            return {
                "ok": False,
                "message": (f"⚠ Biển số không khớp! Quét: {bien_so_quet} | "
                            f"Khớp gần nhất: {best} ({score}%)"),
                "student": student_info,
                "plate_score": score,
                "rescan": True,
            }

    active_tx = is_vehicle_in_lot(ma_rfid=ma_rfid, bien_so=matched_plate)
    if active_tx is None:
        return {"ok": False, "message": "Không tìm thấy lượt xe đang đỗ để xử lý."}

    if not matched_plate:
        matched_plate = active_tx.get("BienSo") or active_tx.get("bien_so") or matched_plate

    # 4. Khóa xe
    locked = str(student_info.get("tinh_trang", "")).strip() == "Khóa"
    if locked and not force:
        return {
            "ok": False,
            "locked": True,
            "message": f"⛔ XE BỊ KHÓA! Chủ xe: {student_info.get('ho_ten')}",
            "student": student_info,
        }

    # 5. Kiểm tra số dư (kèm phụ phí 24h)
    time_in_str = active_tx.get("ThoiGianVao") or get_entry_time_for_plate(matched_plate)
    fee_info = calc_fee_with_surcharge(time_in_str, now)
    total_fee = fee_info["total"]

    so_du = int(student_info.get("so_du", 0) or 0)
    if (so_du < total_fee) and not force:
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
    ok_log = db_manager.add_exit_log(matched_plate, anh_path, total_fee)
    ok_bal = db_manager.update_rfid_balance(ma_rfid, -total_fee)

    if force:
        append_security_audit(
            "MANUAL_OVERRIDE",
            f"{student_info.get('ma_sv', '-')}/{matched_plate}",
            "SUCCESS" if (ok_log and ok_bal) else "FAILED",
            manual_note or "Mở thủ công",
        )

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
        "manual": force,
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
