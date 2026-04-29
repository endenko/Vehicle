"""
FastAPI Server cho SmartParking Valkyrie
═══════════════════════════════════════════════════════════════
Nhận ảnh từ ESP32-CAM và xử lý OCR/Fuzzy Matching, thay thế hoàn toàn Mock.

QUY TRÌNH 4 GIAI ĐOẠN:
    1. POST /register-student  — GUI quét QR/Barcode, đăng ký ma_sv vào cache
    1.5 GET /check-ir           — Kiểm tra IR sensor có xe không trước khi chờ ESP32
    2. POST /process-plate     — ESP32 gửi ảnh, server xử lý OCR
    3. (Tiếp trong /process-plate) — Fuzzy Match + Nghiệp vụ An ninh
    4. (Tiếp trong /process-plate) — Ghi log + Mở Barie

⚠️ RÀNG BUỘC:
    - Tuyệt đối KHÔNG time.sleep()
    - Dùng httpx async cho mọi request mạng
    - Mọi nhánh rẽ đều INSERT INTO KetQuaQuyetDinh (FK → SinhVien, Xe) trước khi trả response
"""
import asyncio

from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional
import re

from thefuzz import fuzz

# Import các module cục bộ
from smart_parking.config import (
    STORAGE_IN, STORAGE_OUT, API_HOST, API_PORT,
    LICH_SU_XE_VAO_DIR, LICH_SU_XE_RA_DIR, FUZZY_THRESHOLD,
)
from smart_parking.database import db_manager
from smart_parking.ocr_handler import LicensePlateOCR
from gui.utils.hardware import open_barrier, check_ir_sensor_async  # async versions

app = FastAPI(title="SmartParking Valkyrie API", version="2.0 (ESP32 Integration)")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════════
# GLOBAL STATE
# ══════════════════════════════════════════════════════════════
license_plate_ocr = LicensePlateOCR()

# Cache: Lưu ma_sv đang chờ ESP32 bắn ảnh về (theo lane)
active_sessions = {"IN": None, "OUT": None}

# Kết quả xử lý gần nhất (để GUI polling)
lane_results = {"IN": None, "OUT": None}

# Cache ngắn hạn cho IR sensor để tránh đọc lặp khi sensor bị chập/chattering
ir_state_cache = {
    "IN": {"detected": None, "ts": 0.0},
    "OUT": {"detected": None, "ts": 0.0},
}
IR_CACHE_TTL_SECONDS = 1.0

# Cooldown chống chụp ảnh trùng lặp (s) — không chụp lại trong 5s sau lần chụp gần nhất
_last_capture_ts = {"IN": 0.0, "OUT": 0.0}
CAPTURE_COOLDOWN_SECONDS = 5.0


class RegisterRequest(BaseModel):
    ma_sv: str
    lane: str


# ══════════════════════════════════════════════════════════════
# LIFECYCLE
# ══════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    """Khởi tạo khi server bắt đầu"""
    print("═" * 60)
    print("🔐 SmartParking Valkyrie API — ESP32 Integration Mode")
    print("═" * 60)
    db_manager.connect()
    db_manager.ensure_audit_table()
    print("[✓] Server SmartParking API khởi động")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup khi server dừng"""
    db_manager.disconnect()
    print("[✓] Server SmartParking API dừng")


# ══════════════════════════════════════════════════════════════
# UTILITY ENDPOINTS
# ══════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "name": "SmartParking Valkyrie API",
        "version": "2.0 (ESP32 Integration)",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/stats")
async def get_statistics():
    stats = db_manager.get_statistics()
    return {
        "parked_count": stats['parked_count'],
        "exits_today": stats['exits_today'],
        "revenue_today": stats['revenue_today'],
        "timestamp": datetime.now().isoformat()
    }


@app.get("/parked")
async def get_parked_vehicles():
    parked = db_manager.get_parked_vehicles()
    return {"vehicles": parked}


@app.get("/lane-status")
async def get_lane_status(lane: str = Query(...)):
    """API để GUI polling kết quả sau khi ESP32 xử lý xong"""
    return lane_results.get(lane, None) or {"status": "pending"}


# ══════════════════════════════════════════════════════════════
# KIỂM TRA IR SENSOR (Xác nhận có xe trước khi chờ ESP32)
# ══════════════════════════════════════════════════════════════

@app.get("/check-ir")
async def check_ir_endpoint(lane: str = Query(...)):
    """Kiểm tra IR sensor xem có xe đang chắn không.
    
    Trả về:
      - {"detected": true} nếu IR phát hiện có xe
      - {"detected": false} nếu không có xe → GUI hiện lỗi "Không có xe?"
    """
    direction = "in" if lane == "IN" else "out"

    cached = ir_state_cache.get(lane, {})
    now = datetime.now().timestamp()
    cached_detected = cached.get("detected")
    cached_ts = float(cached.get("ts", 0.0) or 0.0)
    if cached_detected is not None and (now - cached_ts) < IR_CACHE_TTL_SECONDS:
        return {"detected": cached_detected, "lane": lane, "cached": True}

    detected = await check_ir_sensor_async(direction)
    ir_state_cache[lane] = {"detected": detected, "ts": now}
    
    # Không set lane_results ở đây — GUI sẽ tự xử lý khi check-ir trả về detected=false
    
    return {"detected": detected, "lane": lane}


# ══════════════════════════════════════════════════════════════
# GIAI ĐOẠN 1: ĐĂNG KÝ SINH VIÊN (GUI → Server)
# ══════════════════════════════════════════════════════════════

@app.post("/register-student")
async def register_student(req: RegisterRequest):
    """
    GIAI ĐOẠN 1: Quét mã sinh viên từ Laptop Camera.
    
    GUI quét QR/Barcode → gửi ma_sv + lane (IN/OUT) → Server cache lại.
    ESP32 sẽ dùng cache này khi gửi ảnh về.
    """
    student = db_manager.get_student_by_id(req.ma_sv)
    if not student:
        raise HTTPException(status_code=404, detail=f"Sinh viên {req.ma_sv} không tồn tại")

    active_sessions[req.lane] = req.ma_sv
    lane_results[req.lane] = None  # Reset kết quả của lane
    print(f"[📌] Đăng ký session: {req.ma_sv} → lane {req.lane}")
    return {
        "status": "registered",
        "ma_sv": req.ma_sv,
        "ho_ten": student['ho_ten'],
        "lane": req.lane,
        "timestamp": datetime.now().isoformat()
    }


# ══════════════════════════════════════════════════════════════
# HELPER: Làm sạch text OCR
# ══════════════════════════════════════════════════════════════

def _clean_plate_text(raw: str) -> str:
    """Chuẩn hóa chuỗi biển số: bỏ dấu, khoảng trắng, ký tự đặc biệt."""
    if not raw:
        return ""
    return re.sub(r'[^A-Z0-9]', '', raw.upper())


def _safe_filename(text: str) -> str:
    """Tạo tên file an toàn từ text OCR."""
    safe = re.sub(r'[^\w\-]', '_', text.strip())
    return safe[:50] if safe else "UNKNOWN"


def _build_evidence_filename(text: str, source: str, timestamp: str) -> str:
    if source in {"google", "tesseract"} and text:
        prefix = f"OCR_Success_{_safe_filename(text)}"
    elif source == "db_fallback" and text:
        prefix = f"DB_FALLBACK_{_safe_filename(text)}"
    else:
        prefix = "UNKNOWN"
    return f"{prefix}_{timestamp}.jpg"


def _resolve_ocr_text(frame, fallback_db_plate: str = None):
    ocr_info = license_plate_ocr.extract_text(frame)
    text = ocr_info.get('text') or ""
    source = ocr_info.get('source', 'none')
    error = ocr_info.get('error')

    if not text and fallback_db_plate:
        text = fallback_db_plate
        source = 'db_fallback'

    text_clean = _clean_plate_text(text)
    return {
        'text': text,
        'text_clean': text_clean,
        'source': source,
        'error': error,
    }


def _normalize_esp32_frame(frame):
    """Chuẩn hóa ảnh từ ESP32:
    1. Lật ngang (để sửa ảnh gương từ camera ESP32-CAM AI-Thinker)
    """
    if frame is None:
        return None
    try:
        # Lật ngang để sửa ảnh gương
        return cv2.flip(frame, 1)
    except Exception as e:
        print(f"[!] Lỗi normalize frame: {e}")
        return frame


# ══════════════════════════════════════════════════════════════
# GIAI ĐOẠN 2+3+4: XỬ LÝ ẢNH TỪ ESP32
# ══════════════════════════════════════════════════════════════

@app.post("/process-plate")
async def process_plate(
    lane: str = Query(...),
    file: UploadFile = File(...)
):
    """
    GIAI ĐOẠN 2+3+4: ESP32 gửi ảnh → OCR → Fuzzy Match → An ninh → Mở Barie.
    
    Flow:
    0. Kiểm tra session + IR sensor
    1. Đọc ảnh ESP32
    2. Google Vision OCR NGAY LẬP TỨC
    3. Đặt tên file = text_ocr + timestamp
    4. Fuzzy matching text_ocr vs bien_so_db
    5. Nghiệp vụ an ninh (xe ma, khóa, giờ, số dư)
    6. Ghi log KetQuaQuyetDinh (FK: MaSV→SinhVien, BienSo→Xe) ở MỌI nhánh
    7. Mở barie nếu thành công
    """
    # ── Bước 0: Kiểm tra session ──────────────────────────────
    student_id = active_sessions.get(lane)
    if not student_id:
        res = {"status": "error", "message": "Chưa quét mã sinh viên", "code": 400}
        lane_results[lane] = res
        return JSONResponse(status_code=400, content=res)

    student = db_manager.get_student_by_id(student_id)
    if not student:
        res = {"status": "error", "message": "Sinh viên không tồn tại", "code": 400}
        lane_results[lane] = res
        return JSONResponse(status_code=400, content=res)

    ho_ten = student['ho_ten']
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Lấy thông tin xe đăng ký từ DB (cần sớm để dùng cho FK audit)
    vehicles = db_manager.get_student_vehicles(student_id)
    bien_so_db = vehicles[0]['bien_so'] if vehicles else None

    try:
        # ── Bước 0.5: Kiểm tra IR Sensor ──────────────────────
        direction = "in" if lane == "IN" else "out"
        ir_detected = await check_ir_sensor_async(direction)
        if not ir_detected:
            msg = "Không phát hiện xe tại cổng! IR Sensor không bị chắn."
            db_manager.log_audit_decision(
                student_id, ho_ten, bien_so_db, msg,
                bien_so_ocr="", lane=lane
            )
            active_sessions[lane] = None
            res = {"status": "error", "message": msg, "code": 404}
            lane_results[lane] = res
            return JSONResponse(status_code=404, content=res)

        # ── Bước 1: Đọc ảnh ESP32 ─────────────────────────────
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            db_manager.log_audit_decision(
                student_id, ho_ten, bien_so_db, "Lỗi: Không đọc được file ảnh ESP32",
                bien_so_ocr="", lane=lane
            )
            res = {"status": "error", "message": "Ảnh không hợp lệ", "code": 400}
            lane_results[lane] = res
            return JSONResponse(status_code=400, content=res)

        frame = _normalize_esp32_frame(frame)

        # ── Bước 2: Roboflow detect + Google Vision ưu tiên + Tesseract fallback
        ocr_context = _resolve_ocr_text(frame, fallback_db_plate=bien_so_db)
        text_ocr = ocr_context['text']
        text_ocr_clean = ocr_context['text_clean']
        ocr_source = ocr_context['source']

        print(f"[🔍] OCR source: {ocr_source}, text: '{text_ocr}', cleaned: '{text_ocr_clean}'")

        # ── Bước 3: Đặt tên file bằng kết quả OCR hoặc fallback DB
        filename = _build_evidence_filename(text_ocr_clean, ocr_source, timestamp)
        save_dir = LICH_SU_XE_VAO_DIR if lane == "IN" else LICH_SU_XE_RA_DIR

        save_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{filename}"
        final_path = save_dir / filename
        cv2.imwrite(str(final_path), frame)
        preview_path = final_path
        if lane == "IN":
            preview_path = STORAGE_IN / filename
            cv2.imwrite(str(preview_path), frame)
        print(f"[💾] Lưu ảnh: {final_path}")

        # ── Bước 4: Lấy thông tin DB ──────────────────────────
        rfid_info = db_manager.get_rfid_by_student(student_id)

        if not rfid_info or not vehicles:
            msg = "Lỗi: Thiếu dữ liệu RFID hoặc Xe đăng ký"
            db_manager.log_audit_decision(
                student_id, ho_ten, bien_so_db, msg,
                bien_so_ocr=text_ocr_clean, lane=lane
            )
            res = {"status": "error", "message": msg, "code": 400}
            lane_results[lane] = res
            return JSONResponse(status_code=400, content=res)

        tinh_trang_xe = vehicles[0]['tinh_trang']
        bien_so_db_clean = _clean_plate_text(bien_so_db)
        active_entry = db_manager.get_active_entry_by_rfid(rfid_info['ma_rfid'])

        # ══════════════════════════════════════════════════════
        # LUỒNG VÀO (lane=IN)
        # ══════════════════════════════════════════════════════
        if lane == "IN":
            if active_entry:
                msg = "Từ chối: Xe đã có lượt vào đang đỗ"
                db_manager.log_audit_decision(
                    student_id, ho_ten, bien_so_db, msg,
                    bien_so_ocr=text_ocr_clean, lane="IN"
                )
                res = {"status": "error", "message": msg, "code": 400}
                lane_results[lane] = res
                return JSONResponse(status_code=400, content=res)

            # ✅ THÀNH CÔNG VÀO: dùng bien_so_db gốc cho FK, không dùng bản cleaned
            db_manager.add_entry_log(rfid_info['ma_rfid'], bien_so_db, str(final_path))
            msg = "Chụp ảnh xe vào thành công"
            db_manager.log_audit_decision(
                student_id, ho_ten, bien_so_db, msg,
                bien_so_ocr=text_ocr_clean, lane="IN"
            )

            # Xóa session sau khi xử lý xong
            active_sessions[lane] = None

            asyncio.create_task(open_barrier())

            res = {
                "status": "accepted",
                "message": msg,
                "code": 200,
                "plate": bien_so_db,
                "ocr_text": text_ocr,
                "score": 100,
                "image_path": str(preview_path),
                "history_image_path": str(final_path),
            }
            lane_results[lane] = res
            return JSONResponse(status_code=200, content=res)

        # ══════════════════════════════════════════════════════
        # LUỒNG RA (lane=OUT)
        # ══════════════════════════════════════════════════════
        elif lane == "OUT":
            # Kiểm tra Khóa xe → 403
            if tinh_trang_xe == "Khóa":
                msg = "Từ chối: Tài khoản bị khóa"
                db_manager.log_audit_decision(
                    student_id, ho_ten, bien_so_db, msg,
                    bien_so_ocr=text_ocr_clean, lane="OUT"
                )
                res = {"status": "rejected", "message": msg, "code": 403}
                lane_results[lane] = res
                return JSONResponse(status_code=403, content=res)

            # Kiểm tra có lượt vào không
            if not active_entry:
                msg = "Từ chối: Không tìm thấy lượt vào của xe này hoặc chưa quét mã ở cổng vào"
                db_manager.log_audit_decision(
                    student_id, ho_ten, bien_so_db, msg,
                    bien_so_ocr=text_ocr_clean, lane="OUT"
                )
                res = {"status": "error", "message": msg, "code": 400}
                lane_results[lane] = res
                return JSONResponse(status_code=400, content=res)

            # Kiểm tra giờ hoạt động (6h-23h)
            now = datetime.now()
            current_time = now.hour + now.minute / 60.0
            if not (6.0 <= current_time <= 23.0):
                msg = "Từ chối: Quá 23h không nhận xe ra"
                db_manager.log_audit_decision(
                    student_id, ho_ten, bien_so_db, msg,
                    bien_so_ocr=text_ocr_clean, lane="OUT"
                )
                res = {"status": "rejected", "message": msg, "code": 403}
                lane_results[lane] = res
                return JSONResponse(status_code=403, content=res)

            # Fuzzy Match Luồng RA: so khớp biển số chụp lúc ra với biển số đã lưu lúc vào
            bien_so_khi_vao = active_entry.get('bien_so', '')
            bien_so_vao_clean = _clean_plate_text(bien_so_khi_vao)

            best_score = fuzz.ratio(text_ocr_clean, bien_so_vao_clean) if (text_ocr_clean and bien_so_vao_clean) else 0

            if best_score < FUZZY_THRESHOLD:
                msg = f"Cảnh báo: Không khớp biển số lúc vào (<{FUZZY_THRESHOLD}%) - Score: {best_score}%"
                db_manager.log_audit_decision(
                    student_id, ho_ten, bien_so_db, msg,
                    bien_so_ocr=text_ocr_clean, lane="OUT"
                )
                res = {"status": "rejected", "message": msg, "score": best_score, "code": 406}
                lane_results[lane] = res
                return JSONResponse(status_code=406, content=res)

            # Tính phí phức hợp
            thoi_gian_vao_str = active_entry.get('thoi_gian_vao', '')
            try:
                thoi_gian_vao = datetime.fromisoformat(str(thoi_gian_vao_str))
            except (ValueError, TypeError):
                thoi_gian_vao = now

            duration = now - thoi_gian_vao
            hours = duration.total_seconds() / 3600.0

            # Khung giờ phí
            if 6.0 <= current_time < 17.5:
                fee = 2000
            elif 17.5 <= current_time <= 23.0:
                fee = 3000
            else:
                fee = 3000  # Fallback

            # Phụ phí đỗ qua đêm (>24h)
            if hours > 24:
                fee += 5000

            # Kiểm tra số dư → 402
            if rfid_info['so_du'] < fee:
                msg = f"Từ chối: Số dư không đủ (Cần: {fee:,}đ, Còn: {rfid_info['so_du']:,}đ)"
                db_manager.log_audit_decision(
                    student_id, ho_ten, bien_so_db, msg,
                    bien_so_ocr=text_ocr_clean, lane="OUT"
                )
                res = {"status": "error", "message": msg, "code": 402, "fee": fee, "balance": rfid_info['so_du']}
                lane_results[lane] = res
                return JSONResponse(status_code=402, content=res)

            # ✅ THÀNH CÔNG RA
            db_manager.update_rfid_balance(rfid_info['ma_rfid'], -fee)
            db_manager.add_exit_log(bien_so_khi_vao, str(final_path), fee)

            msg = f"Đã ra - Mở Barie (Phí: {fee:,}đ)"
            db_manager.log_audit_decision(
                student_id, ho_ten, bien_so_db, msg,
                bien_so_ocr=text_ocr_clean, lane="OUT"
            )

            asyncio.create_task(open_barrier())

            # Xóa session sau khi xử lý xong
            active_sessions[lane] = None

            res = {
                "status": "accepted",
                "message": msg,
                "fee": fee,
                "code": 200,
                "plate": bien_so_khi_vao,
                "ocr_text": text_ocr,
                "score": best_score,
                "hours_parked": round(hours, 1),
                "image_path": str(final_path),
            }
            lane_results[lane] = res
            return JSONResponse(status_code=200, content=res)

    except Exception as e:
        print(f"[✗] Lỗi xử lý ảnh: {e}")
        import traceback
        traceback.print_exc()
        # Ghi audit cho lỗi hệ thống
        try:
            db_manager.log_audit_decision(
                student_id, ho_ten, bien_so_db, f"Lỗi hệ thống: {str(e)}",
                bien_so_ocr="", lane=lane
            )
        except Exception:
            pass
        res = {"status": "error", "message": str(e), "code": 500}
        lane_results[lane] = res
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        active_sessions[lane] = None


# ══════════════════════════════════════════════════════════════
# WEBHOOK: ESP32 IR PHÁT HIỆN XE → Python tự gọi /capture
# ══════════════════════════════════════════════════════════════

@app.get("/api/vehicle-detected")
async def vehicle_detected_webhook(lane: str = Query("IN")):
    """
    ESP32 gọi endpoint này khi IR sensor phát hiện xe.
    
    🔥 CRITICAL: Hàm này phải RETURN NGAY LẬP TỨC (<100ms) để không block ESP32.
    
    Flow:
    1. ✅ Nhận webhook từ ESP32 (1ms)
    2. ✅ Kiểm tra active_sessions (1ms)
    3. ✅ RETURN ngay (HTTP 202 Accepted)
    4. 🔄 Background: Fetch image + OCR + Log (async task)
    """
    print(f"[📡] WEBHOOK /api/vehicle-detected được gọi từ ESP32 → lane={lane}")
    
    student_id = active_sessions.get(lane)
    if not student_id:
        msg = f"IR phát hiện xe nhưng chưa có session (chưa quét mã)"
        print(f"[⚠️] {msg} — lane={lane}")
        return {"status": "ignored", "message": msg, "code": 400}

    print(f"[🚗] ESP32 IR webhook OK: lane={lane}, session={student_id}")

    # Tránh xử lý trùng lặp: kiểm tra status
    current_status = lane_results.get(lane)
    if current_status and current_status.get("status") == "processing":
        print(f"[⏳] Lane {lane} đang xử lý, bỏ qua webhook mới")
        return {"status": "ignored", "message": "Already processing", "code": 409}

    # Cooldown: không chụp lại trong 5s sau lần chụp gần nhất
    import time as _time
    now_ts = _time.time()
    if (now_ts - _last_capture_ts.get(lane, 0.0)) < CAPTURE_COOLDOWN_SECONDS:
        elapsed = round(now_ts - _last_capture_ts[lane], 1)
        print(f"[⏳] Cooldown: chụp lại quá nhanh (chỉ {elapsed}s sau lần trước), bỏ qua")
        return {"status": "ignored", "message": f"Cooldown ({elapsed}s)", "code": 429}
    _last_capture_ts[lane] = now_ts

    # 🔥 RETURN NGAY → Không block ESP32!
    print(f"[✅] Webhook accepted, xử lý ảnh trong background...")
    lane_results[lane] = {"status": "processing", "message": "Đang chụp ảnh từ ESP32..."}
    
    # Tạo background task xử lý ảnh (không chặn response)
    asyncio.create_task(_process_vehicle_image(lane, student_id))
    
    return {"status": "accepted", "message": "Processing in background", "code": 202}


async def _process_vehicle_image(lane: str, student_id: str):
    """Background task: Fetch image từ ESP32 + OCR + Log."""
    import httpx
    from smart_parking.config import URL_ESP32_CAPTURE_IN, URL_ESP32_CAPTURE_OUT
    
    print(f"\n[🔄] [Background] Bắt đầu xử lý ảnh: lane={lane}, student={student_id}")
    
    student = db_manager.get_student_by_id(student_id)
    if not student:
        msg = "Student không tồn tại"
        print(f"[ERROR] {msg}")
        lane_results[lane] = {"status": "error", "message": msg, "code": 400}
        active_sessions[lane] = None
        return
    
    ho_ten = student['ho_ten']
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    vehicles = db_manager.get_student_vehicles(student_id)
    bien_so_db = vehicles[0]['bien_so'] if vehicles else None

    # Gọi ESP32 /capture để lấy ảnh
    capture_url = URL_ESP32_CAPTURE_IN if lane == "IN" else URL_ESP32_CAPTURE_OUT
    print(f"[📷] Gọi ESP32 capture: {capture_url}")
    
    image_bytes = None
    try:
        async with httpx.AsyncClient() as client:
            print(f"[⏳] Chờ ảnh từ ESP32 (timeout 5s)...")
            capture_resp = await client.get(capture_url, timeout=10.0)

        if capture_resp.status_code != 200:
            msg = f"❌ ESP32 /capture HTTP {capture_resp.status_code}"
            print(f"[ERROR] {msg}")
            db_manager.log_audit_decision(
                student_id, ho_ten, bien_so_db or "UNKNOWN",
                f"Lỗi capture: {msg}", bien_so_ocr="", lane=lane
            )
            lane_results[lane] = {"status": "error", "message": msg, "code": 502}
            active_sessions[lane] = None
            return

        image_bytes = capture_resp.content
        print(f"[✅] Nhận ảnh từ ESP32: {len(image_bytes)} bytes")

    except asyncio.TimeoutError:
        msg = "❌ Timeout chờ ảnh từ ESP32 (>5s) - Camera không phản hồi"
        print(f"[ERROR] {msg}")
        db_manager.log_audit_decision(
            student_id, ho_ten, bien_so_db or "UNKNOWN",
            msg, bien_so_ocr="", lane=lane
        )
        lane_results[lane] = {"status": "error", "message": msg, "code": 504}
        active_sessions[lane] = None
        return
    except Exception as e:
        msg = f"❌ Lỗi capture ESP32: {str(e)}"
        print(f"[ERROR] {msg}")
        db_manager.log_audit_decision(
            student_id, ho_ten, bien_so_db or "UNKNOWN",
            msg, bien_so_ocr="", lane=lane
        )
        lane_results[lane] = {"status": "error", "message": msg, "code": 502}
        active_sessions[lane] = None
        return

    # Decode & Normalize ảnh
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            msg = "❌ Lỗi: Ảnh ESP32 không decode được"
            print(f"[ERROR] {msg}")
            db_manager.log_audit_decision(
                student_id, ho_ten, bien_so_db or "UNKNOWN",
                msg, bien_so_ocr="", lane=lane
            )
            lane_results[lane] = {"status": "error", "message": msg, "code": 400}
            active_sessions[lane] = None
            return

        frame = _normalize_esp32_frame(frame)

        # ═══════════════════════════════════════════════════════════
        # BƯỚC 1: Chuỗi nghiệp vụ trích xuất OCR có dự phòng
        #   Ưu tiên 1: Roboflow detect + Google Cloud Vision
        #   Ưu tiên 2: Tesseract
        #   Ưu tiên 3: fallback về biển số DB nếu cả hai fail
        # ═══════════════════════════════════════════════════════════
        ocr_context = _resolve_ocr_text(frame, fallback_db_plate=bien_so_db)
        text_ocr = ocr_context['text']
        text_ocr_clean = ocr_context['text_clean']
        ocr_source = ocr_context['source']

        print(f"[🔍] OCR source: {ocr_source}, text: '{text_ocr}', cleaned: '{text_ocr_clean}'")

        # ═══════════════════════════════════════════════════════════
        # BƯỚC 2: Đặt tên vật chứng theo kết quả OCR hoặc fallback DB
        # ═══════════════════════════════════════════════════════════
        filename = _build_evidence_filename(text_ocr_clean, ocr_source, timestamp)
        save_dir = LICH_SU_XE_VAO_DIR if lane == "IN" else LICH_SU_XE_RA_DIR
        save_dir.mkdir(parents=True, exist_ok=True)
        final_path = save_dir / filename
        cv2.imwrite(str(final_path), frame)
        print(f"[💾] Lưu ảnh: {final_path}")

        # Tùy luồng: IN hoặc OUT
        if lane == "IN":
            await _handle_inbound_lane(final_path, student_id, ho_ten, bien_so_db, text_ocr, text_ocr_clean, lane, timestamp)
        elif lane == "OUT":
            await _handle_outbound_lane(final_path, student_id, ho_ten, bien_so_db, text_ocr, text_ocr_clean, lane, timestamp)
        else:
            lane_results[lane] = {"status": "error", "message": f"Unknown lane: {lane}", "code": 400}

        active_sessions[lane] = None

    except Exception as e:
        msg = f"❌ Lỗi xử lý ảnh: {str(e)}"
        print(f"[ERROR] {msg}")
        db_manager.log_audit_decision(
            student_id, ho_ten, bien_so_db or "UNKNOWN",
            msg, bien_so_ocr="", lane=lane
        )
        lane_results[lane] = {"status": "error", "message": msg, "code": 500}
        active_sessions[lane] = None


async def _handle_inbound_lane(final_path, student_id, ho_ten, bien_so_db, text_ocr, text_ocr_clean, lane, timestamp):
    """Xử lý luồng VÀO."""
    print(f"[📥] Xử lý luồng VÀO...")
    
    # Kiểm tra xe đã trong bãi chưa
    rfid_info = db_manager.get_rfid_by_student(student_id)
    if rfid_info:
        active_entry = db_manager.get_active_entry_by_rfid(rfid_info['ma_rfid'])
        if active_entry:
            msg = "❌ Từ chối: Xe đã có lượt vào đang đỗ"
            print(f"[ERROR] {msg}")
            db_manager.log_audit_decision(student_id, ho_ten, bien_so_db, msg, bien_so_ocr=text_ocr_clean, lane=lane)
            lane_results[lane] = {"status": "error", "message": msg, "code": 400}
            return

    # ✅ OK → INSERT entry log (dùng bien_so_db gốc cho FK, không dùng bản cleaned)
    if rfid_info:
        db_manager.add_entry_log(rfid_info['ma_rfid'], bien_so_db or "UNKNOWN", str(final_path))
    
    msg = "✅ Chụp ảnh xe vào thành công"
    print(f"[SUCCESS] {msg}")
    db_manager.log_audit_decision(student_id, ho_ten, bien_so_db, msg, bien_so_ocr=text_ocr_clean, lane=lane)
    
    asyncio.create_task(open_barrier())
    lane_results[lane] = {
        "status": "accepted",
        "message": msg,
        "code": 200,
        "plate": bien_so_db or "UNKNOWN",
        "ocr_text": text_ocr,
        "score": 100,
        "image_path": str(final_path)
    }


async def _handle_outbound_lane(final_path, student_id, ho_ten, bien_so_db, text_ocr, text_ocr_clean, lane, timestamp):
    """
    Xử lý luồng RA — Giao thức Đối soát Chéo.
    So khớp biển số OCR lúc ra với 2 nguồn:
      (a) Biển số đăng ký trong Database (bien_so_db).
      (b) Tiền tố OCR từ tên file ảnh lúc VÀO (truy xuất từ LichSuVaoRa.AnhVao).
    Chỉ mở cổng khi ít nhất 1 trong 2 nguồn đạt >= 75% fuzz.ratio.
    """
    print(f"[📤] Xử lý luồng RA...")
    
    # ── Bước 1: Kiểm tra thông tin RFID ──
    rfid_info = db_manager.get_rfid_by_student(student_id)
    if not rfid_info:
        msg = "Từ chối: Không tìm thấy thông tin RFID"
        print(f"[ERROR] {msg}")
        db_manager.log_audit_decision(student_id, ho_ten, bien_so_db, msg, bien_so_ocr=text_ocr_clean, lane=lane)
        lane_results[lane] = {"status": "error", "message": msg, "code": 400}
        return

    # ── Bước 2: Kiểm tra có lượt vào hợp lệ không ──
    active_entry = db_manager.get_active_entry_by_rfid(rfid_info['ma_rfid'])
    if not active_entry:
        msg = "Từ chối: Không tìm thấy lượt vào của xe này hoặc chưa quét mã ở cổng vào"
        print(f"[ERROR] {msg}")
        db_manager.log_audit_decision(student_id, ho_ten, bien_so_db, msg, bien_so_ocr=text_ocr_clean, lane=lane)
        lane_results[lane] = {"status": "error", "message": msg, "code": 400}
        return

    # ── Bước 3: Kiểm tra tài khoản bị khóa ──
    vehicles = db_manager.get_student_vehicles(student_id)
    if vehicles:
        tinh_trang_xe = vehicles[0].get('tinh_trang', 'Bình thường')
        if tinh_trang_xe == "Khóa":
            msg = "Từ chối: Tài khoản bị khóa"
            print(f"[ERROR] {msg}")
            db_manager.log_audit_decision(student_id, ho_ten, bien_so_db, msg, bien_so_ocr=text_ocr_clean, lane=lane)
            lane_results[lane] = {"status": "rejected", "message": msg, "code": 403}
            return

    # ── Bước 4: Kiểm tra giờ hoạt động (6h-23h) ──
    from smart_parking.config import os
    time_limit_str = os.getenv("TIME_LIMITED_23H_6H", "0")
    if time_limit_str == "1":
        now = datetime.now()
        current_time = now.hour + now.minute / 60.0
        if not (6.0 <= current_time <= 23.0):
            msg = "Từ chối: Quá 23h không nhận xe ra"
            print(f"[ERROR] {msg}")
            db_manager.log_audit_decision(student_id, ho_ten, bien_so_db, msg, bien_so_ocr=text_ocr_clean, lane=lane)
            lane_results[lane] = {"status": "rejected", "message": msg, "code": 403}
            return

    # ═══════════════════════════════════════════════════════════
    # BƯỚC 5: Giao thức Đối soát Chéo (Cross-Reference Fuzzy Match)
    #
    # Nguồn A: Biển số đăng ký trong Database (bien_so_db)
    # Nguồn B: Tiền tố OCR từ tên file ảnh lúc VÀO (split('_')[0])
    #
    # Lấy điểm cao nhất từ 2 nguồn. Chỉ mở cổng khi >= 75%.
    # ═══════════════════════════════════════════════════════════
    
    # --- Nguồn A: biển số đăng ký trong DB ---
    bien_so_db_clean = _clean_plate_text(bien_so_db) if bien_so_db else ""
    score_vs_db = fuzz.ratio(text_ocr_clean, bien_so_db_clean) if (text_ocr_clean and bien_so_db_clean) else 0
    print(f"[🔍] Đối soát A (vs DB '{bien_so_db}'): {score_vs_db}%")

    # --- Nguồn B: tiền tố OCR từ tên file ảnh lúc VÀO ---
    anh_vao_path = active_entry.get('anh_vao', '') or ''
    entry_filename = Path(anh_vao_path).stem if anh_vao_path else ''  # Bỏ extension
    # Trích xuất phần tiền tố OCR: "99E12268_20260503_091403" → "99E12268"
    entry_ocr_prefix = entry_filename.split('_')[0] if entry_filename else ''
    entry_ocr_clean = _clean_plate_text(entry_ocr_prefix)
    score_vs_entry = fuzz.ratio(text_ocr_clean, entry_ocr_clean) if (text_ocr_clean and entry_ocr_clean) else 0
    print(f"[🔍] Đối soát B (vs ảnh VÀO '{entry_ocr_prefix}'): {score_vs_entry}%")

    # Lấy điểm cao nhất từ 2 nguồn
    best_score = max(score_vs_db, score_vs_entry)
    best_source = "DB" if score_vs_db >= score_vs_entry else "Ảnh VÀO"
    print(f"[📊] Best score: {best_score}% (nguồn: {best_source})")

    if best_score < FUZZY_THRESHOLD:
        msg = (f"Cảnh báo: Không khớp biển số (<{FUZZY_THRESHOLD}%) "
               f"- vs DB: {score_vs_db}%, vs Ảnh VÀO: {score_vs_entry}%")
        print(f"[ERROR] {msg}")
        db_manager.log_audit_decision(student_id, ho_ten, bien_so_db, msg, bien_so_ocr=text_ocr_clean, lane=lane)
        lane_results[lane] = {
            "status": "rejected", "message": msg,
            "score": best_score, "score_vs_db": score_vs_db,
            "score_vs_entry": score_vs_entry, "code": 406
        }
        return

    # ── Bước 6: Tính phí phức hợp ──
    now = datetime.now()
    thoi_gian_vao_str = active_entry.get('thoi_gian_vao', '')
    try:
        thoi_gian_vao = datetime.fromisoformat(str(thoi_gian_vao_str))
    except (ValueError, TypeError):
        thoi_gian_vao = now

    duration = now - thoi_gian_vao
    hours = duration.total_seconds() / 3600.0
    current_time = now.hour + now.minute / 60.0

    # Khung giờ phí
    if 6.0 <= current_time < 17.5:
        fee = 2000
    elif 17.5 <= current_time <= 23.0:
        fee = 3000
    else:
        fee = 3000  # Fallback

    # Phụ phí đỗ qua đêm (>24h)
    if hours > 24:
        fee += 5000

    # ── Bước 7: Kiểm tra số dư → 402 ──
    if rfid_info['so_du'] < fee:
        msg = f"Từ chối: Số dư không đủ (Cần: {fee:,}đ, Còn: {rfid_info['so_du']:,}đ)"
        print(f"[ERROR] {msg}")
        db_manager.log_audit_decision(student_id, ho_ten, bien_so_db, msg, bien_so_ocr=text_ocr_clean, lane=lane)
        lane_results[lane] = {"status": "error", "message": msg, "code": 402, "fee": fee, "balance": rfid_info['so_du']}
        return

    # ═══════════════════════════════════════════════════════════
    # ✅ BƯỚC 8: THÀNH CÔNG RA — Trừ tiền, ghi log, mở barie
    # ═══════════════════════════════════════════════════════════
    bien_so_khi_vao = active_entry.get('bien_so', '')
    db_manager.update_rfid_balance(rfid_info['ma_rfid'], -fee)
    db_manager.add_exit_log(bien_so_khi_vao, str(final_path), fee)

    msg = f"Đã ra - Mở Barie (Phí: {fee:,}đ, Match: {best_score}% [{best_source}])"
    print(f"[SUCCESS] {msg}")
    db_manager.log_audit_decision(student_id, ho_ten, bien_so_db, msg, bien_so_ocr=text_ocr_clean, lane=lane)

    asyncio.create_task(open_barrier())
    
    lane_results[lane] = {
        "status": "accepted",
        "message": msg,
        "fee": fee,
        "code": 200,
        "plate": bien_so_khi_vao,
        "ocr_text": text_ocr,
        "score": best_score,
        "score_vs_db": score_vs_db,
        "score_vs_entry": score_vs_entry,
        "hours_parked": round(hours, 1),
        "image_path": str(final_path)
    }


# ══════════════════════════════════════════════════════════════
# SERVER RUNNER
# ══════════════════════════════════════════════════════════════

def run_api_server(host: str = API_HOST, port: int = API_PORT):
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_api_server()


