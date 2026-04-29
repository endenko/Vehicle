"""
Business logic cho xe vao/ra, tinh phi va cap nhat database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Dict, Optional

from smart_parking.config import MIN_BALANCE_REQUIRED
from smart_parking.database import db_manager
from smart_parking.fuzzy_auth import authenticate_with_ocr, clean_extracted_text


@dataclass
class FeeResult:
    allowed: bool
    fee: int
    message: str


def _resolve_student_from_code(code: str) -> Dict[str, Optional[dict]]:
    code = (code or "").strip()
    if not code:
        return {"student": None, "rfid": None}

    if code.upper().startswith("SV"):
        student = db_manager.get_student_by_id(code.upper())
        rfid = db_manager.get_rfid_by_student(code.upper()) if student else None
        return {"student": student, "rfid": rfid}

    if code.upper().startswith("RFID_"):
        rfid = db_manager.get_rfid_by_code(code.upper())
        student = db_manager.get_student_by_id(rfid["ma_sv"]) if rfid else None
        return {"student": student, "rfid": rfid}

    # fallback: thu tim theo ma SV
    student = db_manager.get_student_by_id(code.upper())
    rfid = db_manager.get_rfid_by_student(code.upper()) if student else None
    return {"student": student, "rfid": rfid}


def calculate_exit_fee(now: Optional[datetime] = None) -> FeeResult:
    now = now or datetime.now()
    t = now.time()
    morning_start = time(6, 0)
    afternoon_end = time(17, 30)
    night_end = time(23, 0)

    if t < morning_start:
        return FeeResult(False, 0, "He thong chua mo (truoc 06:00).")
    if t >= night_end:
        return FeeResult(False, 0, "Sau 23:00 khong nhan xe ra.")

    if morning_start <= t < afternoon_end:
        return FeeResult(True, 2000, "Phi xe ra gio hanh chinh: 2000d")

    return FeeResult(True, 3000, "Phi xe ra buoi toi: 3000d")


def preview_vehicle(qr_code: str, bien_so: str = "") -> Dict[str, object]:
    resolved = _resolve_student_from_code(qr_code)
    student = resolved["student"]
    rfid = resolved["rfid"]

    if not student:
        return {
            "status": "error",
            "message": "Khong tim thay sinh vien tu barcode.",
        }

    vehicles = db_manager.get_student_vehicles(student["ma_sv"])
    vehicle_locked = False
    lock_reason = "-"
    matched_plate = None
    if bien_so:
        for v in vehicles:
            if v["bien_so"].upper() == bien_so.upper():
                matched_plate = v
                vehicle_locked = v["tinh_trang"] == "Khóa"
                if vehicle_locked:
                    lock_reason = "Xe bi khoa"
                break

    return {
        "status": "success",
        "owner_name": student.get("ho_ten"),
        "owner_identity_card": student.get("ma_sv"),
        "owner_balance": rfid.get("so_du") if rfid else "-",
        "owner_class": student.get("lop"),
        "owner_major": student.get("khoa"),
        "owner_phone": student.get("sdt"),
        "vehicle_locked": vehicle_locked,
        "lock_reason": lock_reason,
        "matched_plate": matched_plate["bien_so"] if matched_plate else "-",
    }


def process_entry(
    qr_code: str,
    bien_so: str,
    raw_ocr_text: str,
    lane: str,
    local_image_path: Optional[str] = None,
    iot_image_path: Optional[str] = None,
) -> Dict[str, object]:
    resolved = _resolve_student_from_code(qr_code)
    student = resolved["student"]
    rfid = resolved["rfid"]

    if not student:
        return {
            "status": "error",
            "decision": "deny",
            "message": "Chua co thong tin sinh vien tu barcode.",
        }

    if not rfid:
        return {
            "status": "error",
            "decision": "deny",
            "message": f"Sinh vien {student['ma_sv']} chua co tai khoan RFID.",
        }

    auth = authenticate_with_ocr(student["ma_sv"], raw_ocr_text or bien_so, check_balance=False)
    decision = "allow" if auth["valid"] else "deny"

    plate = auth.get("plate") or bien_so or clean_extracted_text(raw_ocr_text or "")

    if decision == "allow":
        db_manager.add_entry_log(rfid["ma_rfid"], plate, iot_image_path or "")

    return {
        "status": "success" if decision == "allow" else "warning",
        "decision": decision,
        "message": auth.get("message"),
        "lane": lane,
        "owner_name": student.get("ho_ten"),
        "owner_identity_card": student.get("ma_sv"),
        "owner_balance": rfid.get("so_du"),
        "owner_class": student.get("lop"),
        "owner_major": student.get("khoa"),
        "owner_phone": student.get("sdt"),
        "scanned_plate": plate,
        "time_in": datetime.now().isoformat(),
        "entry_iot_image_path": iot_image_path,
        "entry_local_image_path": local_image_path,
    }


def process_exit(
    qr_code: str,
    bien_so: str,
    raw_ocr_text: str,
    lane: str,
    local_image_path: Optional[str] = None,
    iot_image_path: Optional[str] = None,
) -> Dict[str, object]:
    resolved = _resolve_student_from_code(qr_code)
    student = resolved["student"]
    rfid = resolved["rfid"]

    if not student or not rfid:
        return {
            "status": "error",
            "decision": "deny",
            "message": "Khong tim thay thong tin sinh vien/RFID.",
        }

    fee_result = calculate_exit_fee()
    if not fee_result.allowed:
        return {
            "status": "error",
            "decision": "deny",
            "message": fee_result.message,
        }

    auth = authenticate_with_ocr(student["ma_sv"], raw_ocr_text or bien_so, check_balance=True)
    if not auth["valid"]:
        return {
            "status": "error",
            "decision": "deny",
            "message": auth.get("message"),
        }

    plate = auth.get("plate") or bien_so or clean_extracted_text(raw_ocr_text or "")
    active_entry = db_manager.get_active_entry_by_plate(plate)
    if not active_entry:
        return {
            "status": "error",
            "decision": "deny",
            "message": "Khong tim thay xe dang do trong bai.",
        }

    current_balance = int(rfid.get("so_du", 0) or 0)
    if current_balance < fee_result.fee:
        return {
            "status": "error",
            "decision": "deny",
            "message": f"Khong du tien: so du {current_balance} < {fee_result.fee}.",
        }

    db_manager.add_exit_log(plate, iot_image_path or "", fee_result.fee)
    db_manager.update_rfid_balance(rfid["ma_rfid"], -fee_result.fee)

    return {
        "status": "success",
        "decision": "allow",
        "message": fee_result.message,
        "lane": lane,
        "owner_name": student.get("ho_ten"),
        "owner_identity_card": student.get("ma_sv"),
        "owner_balance": current_balance - fee_result.fee,
        "owner_class": student.get("lop"),
        "owner_major": student.get("khoa"),
        "owner_phone": student.get("sdt"),
        "scanned_plate": plate,
        "time_in": active_entry.get("thoi_gian_vao"),
        "time_out": datetime.now().isoformat(),
        "fee": fee_result.fee,
        "entry_image_path": active_entry.get("anh_vao"),
        "exit_image_path": iot_image_path,
    }
