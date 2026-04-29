# SmartParking Valkyrie V2.0 - QUICK START GUIDE 🚀

## ✅ Điều đã hoàn thành

### 1️⃣ **Cấu trúc dự án (Project Structure)**
- ✓ Tạo package `smart_parking/` với kiến trúc chuyên nghiệp
- ✓ Tổ chức thư mục `static/` cho lưu trữ ảnh
- ✓ Tạo thư mục `gui/` cho giao diện

### 2️⃣ **Module cốt lõi (Core Modules)**
- ✓ **config.py** - Cấu hình toàn cục (database, API, camera, fuzzy threshold)
- ✓ **database.py** - Database manager (SQL Server connection, queries, logging)
- ✓ **fuzzy_auth.py** - Fuzzy matching engine (75% threshold matching)
- ✓ **camera_scanner.py** - QR/Barcode scanner (multi-method detection)
- ✓ **ocr_handler.py** - Google Cloud Vision OCR handler
- ✓ **vision_api.py** - FastAPI server (process-plate endpoint)

### 3️⃣ **GUI Components (Giao diện)**
- ✓ **dashboard.py** - Statistics dashboard (full-width header)
  - 🚗 Số xe đang đỗ
  - 🚙 Ra hôm nay
  - 💰 Doanh thu hôm nay
  - 🟢🟡🔴 Status indicator
  - Auto-refresh mỗi 5 giây

- ✓ **main_window.py** - Main GUI application
  - Camera scanner (trái)
  - Parked vehicles list (phải)
  - Real-time video feed
  - Statistics dashboard (header)

### 4️⃣ **Dependencies (Thư viện)**
- ✓ Cài đặt: OpenCV, PIL, thefuzz, pyodbc, FastAPI, Google Vision, zxingcpp

### 5️⃣ **Documentation**
- ✓ **README.md** - Hướng dẫn chính
- ✓ **ESP32_INTEGRATION.md** - Hướng dẫn ESP32-CAM
- ✓ **PROJECT_SUMMARY.py** - Tóm tắt dự án
- ✓ **.env.example** - Cấu hình mẫu
- ✓ **schema.sql** - Database schema
- ✓ **setup.sh** - Automation script

### 6️⃣ **Entry Points**
- ✓ **run.py** - Entry point chính (3 modes: api, gui, all)
- ✓ **test_system.py** - System test suite

---

## 🔧 CÁCH DÙNG

### **Bước 1: Cài đặt dependencies**
```bash
cd /home/minhviet/Documents/TestThuGui

# (Virtual environment nên được setup rồi)
pip install -r requirements.txt
```

### **Bước 2: Cấu hình**
```bash
# Copy .env.example → .env
cp .env.example .env

# Sửa .env với thông tin của bạn:
# - DB_SERVER, DB_USER, DB_PASSWORD
# - API_HOST, API_PORT
# - CAMERA_INDEX
# - FUZZY_THRESHOLD
```

### **Bước 3: Tạo Database**
```bash
# Chạy schema.sql trên SQL Server hoặc:
# sqlcmd -S localhost -U sa -P your_password -i schema.sql
```

### **Bước 4: Google Cloud Vision**
```bash
# Lưu key.json vào thư mục TestThuGui/
# Hoặc cấu hình GOOGLE_APPLICATION_CREDENTIALS
```

### **Bước 5: Chạy ứng dụng**
```bash
# Mode all (GUI + API) - RECOMMENDED
python run.py all

# Hoặc chỉ GUI
python run.py gui

# Hoặc chỉ API server
python run.py api --port 8000
```

### **Bước 6: Test**
```bash
# Quick test
python test_system.py

# Test database
python test_system.py --db

# Test camera
python test_system.py --camera
```

---

## 📋 QUY TRÌNH LÀM VIỆC

### **Giai đoạn 1: Quét mã sinh viên (Laptop)**
```
1. Sinh viên quét QR/Barcode qua webcam laptop
2. Hệ thống nhận diện → Trích ma_sv
3. Gửi yêu cầu POST đến /register-student
4. Lưu ma_sv để gửi cho ESP32
```

### **Giai đoạn 2: Chụp ảnh biển số (ESP32)**
```
1. Cảm biến IR phát hiện xe
2. ESP32 chụp ảnh biển số
3. POST ảnh + ma_sv đến /process-plate
4. API nhận ảnh → Gọi Google Vision OCR
```

### **Giai đoạn 3: Xác thực (Fuzzy Matching)**
```
1. OCR trích xuất text (có thể mờ)
2. Fuzzy matching so khớp với danh sách xe của sinh viên
3. Nếu ≥75% → CHẤP NHẬN
4. Nếu <75% → TỪ CHỐI
```

### **Giai đoạn 4: Ghi log & mở barrier**
```
1. Ghi log vào database (LichSuVaoRa)
2. Gửi lệnh mở barrier đến ESP32
3. Cập nhật statistics dashboard (real-time)
```

---

## 🌐 API ENDPOINTS (FastAPI)

```
GET  /health              → Health check
GET  /stats               → Thống kê (xe đỗ, ra hôm nay, doanh thu)
GET  /parked              → Danh sách xe đang đỗ
POST /process-plate       → Xử lý ảnh từ ESP32
POST /register-student    → Đăng ký sinh viên từ Camera
```

**Ví dụ:**
```bash
# Get stats
curl http://127.0.0.1:8000/stats

# Process plate from ESP32
curl -X POST \
  -F "file=@image.jpg" \
  -F "ma_sv=SV21001" \
  http://127.0.0.1:8000/process-plate

# Register student from Camera
curl -X POST \
  "http://127.0.0.1:8000/register-student?ma_sv=SV21001"
```

---

## 📊 DATABASE

**Tables:**
- `SinhVien` - Thông tin sinh viên
- `Xe` - Danh sách xe đã đăng ký
- `TheRFID` - Thẻ RFID (tùy chọn)
- `LichSuVaoRa` - Log vào/ra xe

**Sample data:** 5 sinh viên, 5 xe (trong schema.sql)

---

## 🧪 TEST

```bash
# Kiểm tra imports
python test_system.py

# Kiểm tra database
python test_system.py --db

# Kiểm tra camera
python test_system.py --camera
```

---

## ⚙️ CONFIGURATION

File `.env` (tạo từ `.env.example`):
```
DB_SERVER=localhost              # SQL Server hostname
DB_NAME=SmartParking_Valkyrie    # Database name
DB_USER=sa                       # SQL Server user
DB_PASSWORD=yourpassword         # SQL Server password
DB_TRUSTED_CONNECTION=no         # Windows Auth

API_HOST=127.0.0.1               # API server IP
API_PORT=8000                    # API server port

CAMERA_INDEX=0                   # Webcam index (0, 1, 2...)
FUZZY_THRESHOLD=75               # % confidence for matching
LOG_LEVEL=INFO                   # Logging level
```

---

## 🔗 ESP32-CAM INTEGRATION

Chi tiết: [ESP32_INTEGRATION.md](ESP32_INTEGRATION.md)

**Flow:**
```
ESP32-CAM
  ↓ [IR Trigger]
  ↓ [Chụp ảnh]
  ↓ [POST ảnh → /process-plate]
  ↓
FastAPI Server
  ↓ [Google Vision OCR]
  ↓ [Fuzzy Matching]
  ↓ [Ghi log database]
  ↓
Response: accepted/rejected
  ↓
ESP32-CAM
  ↓ [Servo: Mở/Đóng barrier]
```

---

## 📁 FILE STRUCTURE

```
TestThuGui/
├── smart_parking/              # Main package
│   ├── __init__.py
│   ├── config.py               # Configuration
│   ├── database.py             # Database manager
│   ├── fuzzy_auth.py           # Fuzzy matching
│   ├── camera_scanner.py       # QR/Barcode scanner
│   ├── ocr_handler.py          # Google Vision
│   ├── vision_api.py           # FastAPI server
│   ├── gui/
│   │   ├── dashboard.py        # Statistics dashboard
│   │   └── main_window.py      # Main GUI
│   └── models/
│       └── __init__.py
├── static/                     # Image storage
│   ├── in/
│   ├── out/
│   └── tmp/
├── run.py                      # Entry point
├── test_system.py              # Tests
├── setup.sh                    # Setup script
├── schema.sql                  # Database schema
├── requirements.txt            # Dependencies
├── .env.example                # Config template
├── README.md                   # Main docs
├── ESP32_INTEGRATION.md        # ESP32 guide
└── PROJECT_SUMMARY.py          # Project summary
```

---

## 🐛 TROUBLESHOOTING

| Problem | Solution |
|---------|----------|
| Camera không mở | Kiểm tra CAMERA_INDEX trong .env |
| DB không kết nối | Kiểm tra SQL Server + credentials |
| zxingcpp error | `pip install zxing-cpp` |
| Vision API error | Kiểm tra key.json + GCP quota |
| Port 8000 dùng | `python run.py api --port 9000` |

---

## 📞 NEXT STEPS

1. **Cấu hình database** → Chạy schema.sql
2. **Cấu hình Google Cloud Vision** → Lưu key.json
3. **Chạy ứng dụng** → `python run.py all`
4. **Test quét QR** → Dùng điện thoại quét mã SV
5. **Tích hợp ESP32** → Xem ESP32_INTEGRATION.md
6. **Tùy chỉnh** → Sửa fuzzy threshold, colors, etc.

---

**Made with ❤️ by Sensei - April 2026**
