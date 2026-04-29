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
from smart_parking.ocr_handler import GoogleVisionOCR
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
vision_ocr = GoogleVisionOCR()

# Cache: Lưu ma_sv đang chờ ESP32 bắn ảnh về (theo lane)
active_sessions = {"IN": None, "OUT": None}

# Kết quả xử lý gần nhất (để GUI polling)
lane_results = {"IN": None, "OUT": None}


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
    detected = await check_ir_sensor_async(direction)
    
    if not detected:
        # Hủy session nếu không có xe
        active_sessions[lane] = None
        lane_results[lane] = {
            "status": "error",
            "message": "Không phát hiện xe tại cổng. Vui lòng đưa xe vào vùng cảm biến.",
            "code": 404,
        }
    
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

        # ── Bước 2: Google Vision OCR NGAY LẬP TỨC ────────────
        ocr_result = vision_ocr.extract_text(frame)
        text_ocr = ocr_result if ocr_result else ""
        text_ocr_clean = _clean_plate_text(text_ocr)

        # ── Bước 3: Đặt tên file bằng text_ocr ────────────────
        if text_ocr_clean:
            file_prefix = _safe_filename(text_ocr_clean)
        else:
            file_prefix = "UNKNOWN"

        if lane == "IN":
            save_dir = LICH_SU_XE_VAO_DIR
        else:
            save_dir = LICH_SU_XE_RA_DIR

        save_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{file_prefix}_{timestamp}.jpg"
        final_path = save_dir / filename
        cv2.imwrite(str(final_path), frame)
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

        # ── Bước 5: Fuzzy Matching ────────────────────────────
        active_entry = db_manager.get_active_entry_by_plate(bien_so_db)

        # So khớp text_ocr vs bien_so_db đăng ký
        match_score_db = fuzz.ratio(text_ocr_clean, bien_so_db_clean) if text_ocr_clean else 0

        # ══════════════════════════════════════════════════════
        # LUỒNG VÀO (lane=IN)
        # ══════════════════════════════════════════════════════
        if lane == "IN":
            # Kiểm tra Xe Ma (đã có bản ghi đang đỗ)
            if active_entry:
                msg = "Từ chối: Xe ma (Xe đang trong bãi)"
                db_manager.log_audit_decision(
                    student_id, ho_ten, bien_so_db, msg,
                    bien_so_ocr=text_ocr_clean, lane="IN"
                )
                res = {"status": "error", "message": msg, "code": 400}
                lane_results[lane] = res
                return JSONResponse(status_code=400, content=res)

            # Kiểm tra Fuzzy Match >= 75%
            if match_score_db < FUZZY_THRESHOLD:
                msg = f"Cảnh báo: Không khớp biển số (<{FUZZY_THRESHOLD}%) - Score: {match_score_db}%"
                db_manager.log_audit_decision(
                    student_id, ho_ten, bien_so_db, msg,
                    bien_so_ocr=text_ocr_clean, lane="IN"
                )
                res = {"status": "rejected", "message": msg, "score": match_score_db, "code": 406}
                lane_results[lane] = res
                return JSONResponse(status_code=406, content=res)

            # ✅ THÀNH CÔNG VÀO
            db_manager.add_entry_log(rfid_info['ma_rfid'], bien_so_db, str(final_path))
            msg = "Cho phép xe vào"
            db_manager.log_audit_decision(
                student_id, ho_ten, bien_so_db, msg,
                bien_so_ocr=text_ocr_clean, lane="IN"
            )

            await open_barrier()

            # Xóa session sau khi xử lý xong
            active_sessions[lane] = None

            res = {
                "status": "accepted",
                "message": msg,
                "code": 200,
                "plate": bien_so_db,
                "ocr_text": text_ocr,
                "score": match_score_db,
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
                msg = "Từ chối: Không tìm thấy lượt vào của xe này"
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

            # Fuzzy Match nâng cao cho Luồng RA:
            # So khớp text_ocr vs (1) BienSo đăng ký DB và (2) BienSo lúc xe vào
            bien_so_khi_vao = active_entry.get('bien_so', '')
            bien_so_vao_clean = _clean_plate_text(bien_so_khi_vao)

            match_score_vao = fuzz.ratio(text_ocr_clean, bien_so_vao_clean) if (text_ocr_clean and bien_so_vao_clean) else 0

            # Lấy score cao nhất giữa 2 phép so
            best_score = max(match_score_db, match_score_vao)

            if best_score < FUZZY_THRESHOLD:
                msg = f"Cảnh báo: Không khớp biển số (<{FUZZY_THRESHOLD}%) - Score DB: {match_score_db}%, Score Vào: {match_score_vao}%"
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
            db_manager.add_exit_log(bien_so_db, str(final_path), fee)

            msg = f"Đã ra - Mở Barie (Phí: {fee:,}đ)"
            db_manager.log_audit_decision(
                student_id, ho_ten, bien_so_db, msg,
                bien_so_ocr=text_ocr_clean, lane="OUT"
            )

            await open_barrier()

            # Xóa session sau khi xử lý xong
            active_sessions[lane] = None

            res = {
                "status": "accepted",
                "message": msg,
                "fee": fee,
                "code": 200,
                "plate": bien_so_db,
                "ocr_text": text_ocr,
                "score": best_score,
                "hours_parked": round(hours, 1),
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


# ══════════════════════════════════════════════════════════════
# SERVER RUNNER
# ══════════════════════════════════════════════════════════════

def run_api_server(host: str = API_HOST, port: int = API_PORT):
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_api_server()
