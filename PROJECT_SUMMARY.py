"""
Tóm tắt cấu trúc dự án SmartParking Valkyrie V2.0
Generated: April 2026
"""

PROJECT_STRUCTURE = """
/home/minhviet/Documents/TestThuGui/
│
├── 📦 smart_parking/                    # Main package
│   ├── __init__.py                      # Package init
│   ├── config.py                        # ⚙️  Cấu hình toàn cục
│   ├── database.py                      # 🗄️  Database manager (SQL Server)
│   ├── fuzzy_auth.py                    # 🔍 Fuzzy matching engine
│   ├── camera_scanner.py                # 📷 QR/Barcode scanner
│   ├── ocr_handler.py                   # 🔤 Google Vision OCR
│   ├── vision_api.py                    # 🌐 FastAPI server (ESP32 endpoint)
│   │
│   ├── 🖼️  gui/
│   │   ├── __init__.py
│   │   ├── dashboard.py                 # 📊 Statistics dashboard widget
│   │   └── main_window.py               # 🖥️  Main GUI application
│   │
│   └── 📊 models/
│       └── __init__.py                  # (Sẵn sàng cho SQLAlchemy ORM)
│
├── 📁 static/                           # Storage directory
│   ├── in/                              # Ảnh vào xe
│   ├── out/                             # Ảnh ra xe
│   └── tmp/                             # Ảnh tạm thời
│
├── ▶️  run.py                           # Entry point chính
├── 🧪 test_system.py                    # System test suite
├── 🛠️  setup.sh                         # Setup automation script
├── 📋 schema.sql                        # SQL Server database schema
│
├── 📦 requirements.txt                  # Python dependencies
├── ⚙️  .env.example                     # Configuration template
├── 📖 README.md                         # Main documentation
├── 📘 ESP32_INTEGRATION.md              # ESP32-CAM integration guide
│
└── ✅ CHANGES.md                        # This file
"""

MAIN_FEATURES = """
=================================================================
SmartParking Valkyrie V2.0 - MAIN FEATURES
=================================================================

✅ 1. STATISTICS DASHBOARD (Full-width header)
   - 🚗 Số xe đang đỗ (real-time)
   - 🚙 Ra hôm nay (tổng cộng)
   - 💰 Doanh thu hôm nay
   - 🟢🟡🔴 Status indicator

✅ 2. CAMERA SCANNER (Left panel)
   - Quét mã QR/Barcode sinh viên
   - Multi-method detection: QR → zxingcpp → OpenCV
   - Real-time video feed

✅ 3. PARKED VEHICLES LIST (Right panel)
   - Danh sách xe đang đỗ
   - Hiển thị sinh viên + lớp + thời gian vào
   - Auto-refresh mỗi 5 giây
   - Click để xem chi tiết

✅ 4. FASTAPI SERVER
   - /process-plate - Nhận ảnh từ ESP32
   - /register-student - Đăng ký sinh viên từ Camera
   - /stats - Lấy thống kê
   - /parked - Danh sách xe đang đỗ
   - /health - Health check

✅ 5. FUZZY MATCHING ENGINE
   - So khớp mờ OCR text với danh sách xe
   - Ngưỡng 75% tự tin
   - Xử lý text rác từ hình ảnh mờ/lỗi

✅ 6. DATABASE INTEGRATION
   - SQL Server connection (pyodbc)
   - Query optimization với indexes
   - Transaction support
   - Sample data included

✅ 7. GOOGLE CLOUD VISION
   - OCR biển số xe
   - Text extraction from images
   - Error handling

=================================================================
"""

INSTALLATION_STEPS = """
=================================================================
HƯỚNG DẪN CÀI ĐẶT & CHẠY
=================================================================

1️⃣  CÀI ĐẶT DEPENDENCIES:
    pip install -r requirements.txt

2️⃣  CẤU HÌNH DATABASE:
    - Cài SQL Server (nếu chưa)
    - Chạy schema.sql để tạo database
    - Sửa .env với credentials

3️⃣  CẤU HÌNH GOOGLE CLOUD:
    - Tải key.json từ GCP
    - Lưu vào TestThuGui/key.json
    - Hoặc điều chỉnh GOOGLE_CREDENTIALS_PATH

4️⃣  CHẠY ỨNG DỤNG:
    python run.py all              # GUI + API
    python run.py gui              # Chỉ GUI
    python run.py api --port 8000  # Chỉ API

5️⃣  TEST:
    python test_system.py          # Quick test
    python test_system.py --db     # Test DB
    python test_system.py --camera # Test camera

=================================================================
"""

API_ENDPOINTS = """
=================================================================
API ENDPOINTS (FastAPI)
=================================================================

GET /
  → Trang chủ API, liệt kê endpoints

GET /health
  → Health check
  Response: {"status": "healthy", "timestamp": "..."}

GET /stats
  → Lấy thống kê hệ thống
  Response: {
    "parked_count": 5,
    "exits_today": 12,
    "revenue_today": 36000,
    "timestamp": "..."
  }

GET /parked
  → Danh sách xe đang đỗ
  Response: {
    "vehicles": [
      {
        "ma_rfid": "RFID_UED_100",
        "bien_so": "43A1-12345",
        "gio_vao": "2026-04-29T10:30:00",
        "ho_ten": "Nguyễn Văn An",
        "lop": "21SPT1"
      },
      ...
    ]
  }

POST /process-plate
  → Xử lý biển số từ ESP32
  Headers: multipart/form-data
  Fields:
    - file: image file (JPEG/PNG)
    - ma_sv: student ID (optional)
  Response (success):
    {
      "status": "accepted",
      "message": "[✓] CHẤP NHẬN (92%): 43A1-12345",
      "plate": "43A1-12345",
      "confidence": 92,
      "student": {...},
      "image_path": "/storage/in/43A1-12345_timestamp.jpg"
    }
  Response (rejected):
    {
      "status": "rejected",
      "message": "[✗] KHÔNG KHỚP BIỂN SỐ...",
      ...
    }

POST /register-student
  → Đăng ký sinh viên (từ Camera)
  Query: ?ma_sv=SV21001
  Response:
    {
      "status": "registered",
      "ma_sv": "SV21001",
      "ho_ten": "Nguyễn Văn An",
      "timestamp": "..."
    }

=================================================================
"""

DATABASE_SCHEMA = """
=================================================================
DATABASE SCHEMA (SQL Server)
=================================================================

TABLE: SinhVien
  ├── MaSV (PK, NVARCHAR 50)
  ├── HoTen (NVARCHAR 100)
  ├── Khoa (NVARCHAR 100)
  ├── Lop (NVARCHAR 50)
  ├── SDT (NVARCHAR 20)
  └── NgayTao (DATETIME)

TABLE: Xe
  ├── BienSo (PK, NVARCHAR 50)
  ├── MaSV (FK → SinhVien)
  ├── LoaiXe (NVARCHAR 100)
  ├── MauSac (NVARCHAR 50)
  ├── TinhTrang (NVARCHAR 20: "Khóa"/"Không Khóa")
  └── NgayTao (DATETIME)

TABLE: TheRFID
  ├── MaRFID (PK, NVARCHAR 50)
  ├── MaSV (FK → SinhVien)
  ├── SoDu (INT)
  ├── TinhTrang (NVARCHAR 20: "Hoạt động"/"Khóa")
  └── NgayTao (DATETIME)

TABLE: LichSuVaoRa
  ├── ID (PK, INT IDENTITY)
  ├── MaRFID (FK → TheRFID)
  ├── BienSo (FK → Xe)
  ├── ThoiGianVao (DATETIME)
  ├── AnhVao (NVARCHAR MAX)
  ├── ThoiGianRa (DATETIME)
  ├── AnhRa (NVARCHAR MAX)
  ├── SoTienTru (INT)
  ├── TrangThai (NVARCHAR 50: "Đang đỗ"/"Đã ra")
  └── NgayTao (DATETIME)

INDEXES:
  ├── IX_Xe_MaSV
  ├── IX_TheRFID_MaSV
  ├── IX_LichSuVaoRa_BienSo
  ├── IX_LichSuVaoRa_TrangThai
  └── IX_LichSuVaoRa_ThoiGianVao

=================================================================
"""

CONFIGURATION = """
=================================================================
CONFIGURATION (.env)
=================================================================

# Database
DB_SERVER=localhost
DB_NAME=SmartParking_Valkyrie
DB_USER=sa
DB_PASSWORD=yourpassword
DB_TRUSTED_CONNECTION=no

# API Server
API_HOST=127.0.0.1
API_PORT=8000

# Camera
CAMERA_INDEX=0

# Fuzzy Matching
FUZZY_THRESHOLD=75

# Logging
LOG_LEVEL=INFO

=================================================================
"""

TROUBLESHOOTING = """
=================================================================
TROUBLESHOOTING
=================================================================

❌ "Cannot open camera"
   → Kiểm tra camera kết nối + quyền truy cập
   → Thay CAMERA_INDEX trong .env (0 → 1 → 2...)

❌ "Cannot connect to database"
   → Kiểm tra SQL Server đang chạy
   → Kiểm tra credentials trong .env
   → Cài ODBC Driver 17 for SQL Server

❌ "zxingcpp not found"
   → pip install zxing-cpp

❌ "Google Vision error"
   → Kiểm tra key.json tồn tại
   → Kiểm tra GCP credentials có hiệu lực

❌ "ModuleNotFoundError"
   → pip install -r requirements.txt
   → source venv/bin/activate

❌ "API port already in use"
   → python run.py api --port 9000  # Dùng port khác

=================================================================
"""

if __name__ == "__main__":
    print("=" * 80)
    print("SmartParking Valkyrie V2.0 - PROJECT SUMMARY")
    print("=" * 80)
    print()
    print(PROJECT_STRUCTURE)
    print()
    print(MAIN_FEATURES)
    print()
    print(INSTALLATION_STEPS)
    print()
    print(API_ENDPOINTS)
    print()
    print(DATABASE_SCHEMA)
    print()
    print(CONFIGURATION)
    print()
    print(TROUBLESHOOTING)
    print()
    print("=" * 80)
    print("✅ Project setup complete!")
    print("   Next: python run.py all")
    print("=" * 80)
