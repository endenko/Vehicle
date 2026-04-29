"""
FastAPI Server cho SmartParking Valkyrie
Nhận ảnh từ ESP32-CAM và xử lý OCR/Fuzzy Matching
"""
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import io
from datetime import datetime
from pathlib import Path
from typing import Optional
import threading

# Import các module cục bộ
from smart_parking.config import STORAGE_IN, STORAGE_OUT, API_HOST, API_PORT
from smart_parking.database import db_manager
from smart_parking.fuzzy_auth import authenticate_with_ocr
from smart_parking.ocr_handler import GoogleVisionOCR

app = FastAPI(title="SmartParking Valkyrie API", version="1.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instance
vision_ocr = GoogleVisionOCR()
last_student_id = None

@app.on_event("startup")
async def startup():
    """Khởi tạo khi server bắt đầu"""
    print("[✓] Server SmartParking API khởi động")
    # Kết nối database
    db_manager.connect()

@app.on_event("shutdown")
async def shutdown():
    """Cleanup khi server dừng"""
    db_manager.disconnect()
    print("[✓] Server SmartParking API dừng")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "SmartParking Valkyrie API",
        "version": "1.0",
        "endpoints": [
            "/process-plate - POST: Xử lý biển số từ ESP32",
            "/stats - GET: Lấy thống kê",
            "/parked - GET: Danh sách xe đang đỗ"
        ]
    }

@app.get("/health")
async def health_check():
    """Kiểm tra sức khỏe server"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/stats")
async def get_statistics():
    """Lấy thống kê hệ thống"""
    stats = db_manager.get_statistics()
    return {
        "parked_count": stats['parked_count'],
        "exits_today": stats['exits_today'],
        "revenue_today": stats['revenue_today'],
        "timestamp": datetime.now().isoformat()
    }

@app.get("/parked")
async def get_parked_vehicles():
    """Danh sách xe đang đỗ"""
    parked = db_manager.get_parked_vehicles()
    return {"vehicles": parked}

@app.post("/process-plate")
async def process_plate(
    file: UploadFile = File(...),
    ma_sv: Optional[str] = Form(None)
):
    """
    Xử lý biển số từ ESP32
    
    - file: Ảnh từ ESP32 (jpeg/png)
    - ma_sv: Mã sinh viên (nếu laptop gửi kèm)
    """
    try:
        # Đọc file ảnh
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise HTTPException(status_code=400, detail="Ảnh không hợp lệ")
        
        # Lưu ảnh vào thư mục tạm
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        temp_path = STORAGE_IN / f"esp32_{timestamp}.jpg"
        cv2.imwrite(str(temp_path), frame)
        
        # Nếu không có ma_sv từ laptop, dùng cái cuối cùng
        student_id = ma_sv or last_student_id
        
        if not student_id:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Chưa có mã sinh viên từ Laptop!",
                    "plate": None
                }
            )
        
        # Gọi Google Vision để OCR
        ocr_result = vision_ocr.extract_text(frame)
        
        if not ocr_result:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Không thể đọc ảnh",
                    "plate": None,
                    "image_path": str(temp_path)
                }
            )
        
        raw_text = ocr_result
        
        # Xác thực bằng fuzzy matching
        auth_result = authenticate_with_ocr(student_id, raw_text)
        
        if auth_result['valid']:
            # Nếu hợp lệ, lưu ảnh vào thư mục IN
            final_path = STORAGE_IN / f"{auth_result['plate']}_{timestamp}.jpg"
            cv2.imwrite(str(final_path), frame)
            
            # Ghi log vào database
            rfid = auth_result['rfid']
            if rfid:
                db_manager.add_entry_log(rfid['ma_rfid'], auth_result['plate'], str(final_path))
            
            return JSONResponse(
                status_code=200,
                content={
                    "status": "accepted",
                    "message": auth_result['message'],
                    "plate": auth_result['plate'],
                    "confidence": auth_result['confidence'],
                    "student": {
                        "ma_sv": auth_result['student']['ma_sv'] if auth_result['student'] else None,
                        "ho_ten": auth_result['student']['ho_ten'] if auth_result['student'] else None
                    },
                    "image_path": str(final_path)
                }
            )
        else:
            return JSONResponse(
                status_code=403,
                content={
                    "status": "rejected",
                    "message": auth_result['message'],
                    "plate": auth_result['plate'],
                    "confidence": auth_result['confidence'],
                    "image_path": str(temp_path)
                }
            )
    
    except Exception as e:
        print(f"[✗] Lỗi xử lý ảnh: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/register-student")
async def register_student(ma_sv: str):
    """
    Đăng ký sinh viên (gọi từ Camera Laptop)
    Lưu ma_sv để ESP32 sử dụng
    """
    global last_student_id
    
    student = db_manager.get_student_by_id(ma_sv)
    if not student:
        raise HTTPException(status_code=404, detail=f"Sinh viên {ma_sv} không tồn tại")
    
    last_student_id = ma_sv
    return {
        "status": "registered",
        "ma_sv": ma_sv,
        "ho_ten": student['ho_ten'],
        "timestamp": datetime.now().isoformat()
    }

def run_api_server(host: str = API_HOST, port: int = API_PORT):
    """Chạy API server"""
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    run_api_server()
