# SmartParking Valkyrie V2.0 🚗🔒

## 📋 Mô tả dự án

Hệ thống quản lý bãi đỗ xe thông minh sử dụng:
- **Laptop Camera**: Quét mã sinh viên (QR/Barcode)
- **ESP32-CAM**: Chụp ảnh biển số xe + cảm biến IR
- **Google Cloud Vision**: OCR nhận diện biển số
- **Fuzzy Matching**: Xác minh sinh viên + xe hợp lệ
- **SQL Server**: Lưu trữ database tập trung

---

## 🏗️ Cấu trúc thư mục

```
TestThuGui/
├── smart_parking/              # Main package
│   ├── __init__.py
│   ├── config.py               # ⚙️ Cấu hình toàn cục
│   ├── database.py             # 🗄️ Database handler (SQL Server)
│   ├── fuzzy_auth.py           # 🔍 Fuzzy matching logic
│   ├── camera_scanner.py       # 📷 QR/Barcode scanner
│   ├── ocr_handler.py          # 🔤 Google Vision OCR
│   ├── vision_api.py           # 🌐 FastAPI server
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── dashboard.py        # 📊 Statistics dashboard
│   │   └── main_window.py      # 🖥️ Main GUI
│   └── models/
│       └── __init__.py         # (Sẵn sàng cho ORM)
├── static/                     # 📁 Lưu trữ ảnh
│   ├── in/                     # Ảnh vào xe
│   ├── out/                    # Ảnh ra xe
│   └── tmp/                    # Ảnh tạm thời
├── run.py                      # ▶️ Entry point chính
├── requirements.txt            # 📦 Dependencies
├── .env.example                # ⚙️ Cấu hình mẫu
└── README.md                   # 📖 Hướng dẫn này
```

---

## 🚀 Cài đặt & Chạy

### 1️⃣ **Yêu cầu hệ thống**
- Python 3.10+
- SQL Server (hoặc cấu hình Windows Auth)
- Google Cloud Vision API key
- Camera laptop (webcam)
- Optional: ESP32-CAM với cảm biến IR

### 2️⃣ **Cài đặt Python dependencies**

```bash
cd /home/minhviet/Documents/TestThuGui

# Tạo virtual environment (nên dùng)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# hoặc
venv\Scripts\activate     # Windows

# Cài đặt dependencies
pip install -r requirements.txt
```

### 3️⃣ **Cấu hình database**

**SQL Server - Tạo database:**
```sql
USE master;
GO

CREATE DATABASE SmartParking_Valkyrie;
GO

USE SmartParking_Valkyrie;
GO

-- [Chạy script từ file schema.sql nếu có]
```

**Cấu hình connection:**
- Copy `.env.example` thành `.env`
- Điều chỉnh `DB_SERVER`, `DB_USER`, `DB_PASSWORD`

### 4️⃣ **Google Cloud Vision API**
1. Tạo GCP project
2. Tải Google Cloud credentials JSON → lưu vào `key.json`
3. Đặt path trong `smart_parking/config.py`

### 5️⃣ **Chạy ứng dụng**

**Chế độ 1: Chỉ GUI (cần API sẵn sàng)**
```bash
python run.py gui
```

**Chế độ 2: Chỉ API server**
```bash
python run.py api --host 127.0.0.1 --port 8000
```

**Chế độ 3: GUI + API (RECOMMENDED)**
```bash
python run.py all
```

---

## 🎯 Quy trình làm việc

### **Giai đoạn 1: Quét mã sinh viên (Laptop Camera)**
1. Sinh viên quét mã QR/Barcode với camera laptop
2. Hệ thống nhận diện mã → Trích xuất mã SV
3. Lưu `ma_sv` để gửi cho ESP32

### **Giai đoạn 2: Xe vào bãi (ESP32-CAM)**
1. Cảm biến IR phát hiện xe → Trigger
2. ESP32 chụp ảnh biển số → POST ảnh đến API
3. API nhận ảnh → Gọi Google Vision OCR

### **Giai đoạn 3: Xác thực & Fuzzy Matching**
1. API nhận OCR text thô (có thể mờ/lỗi)
2. Fuzzy matching so sánh với danh sách xe của sinh viên
3. Nếu khớp ≥75% → **MỞ BARRIER** + ghi log vào
4. Nếu không khớp → **TỪ CHỐI** + cảnh báo

### **Giai đoạn 4: Xe ra bãi**
1. Tương tự, ESP32 chụp ảnh khi xe rời
2. Hệ thống cập nhật status "Đã ra" + Tính tiền

---

## 📊 Dashboard Thống kê

**Header (Full-width):**
- 🚗 **Số xe đang đỗ**: Cập nhật real-time
- 🚙 **Ra hôm nay**: Tổng xe đã thoát hôm nay
- 💰 **Doanh thu hôm nay**: Tính theo thời gian đỗ
- **Status indicator**: Xanh (bình thường), Vàng (gần đầy), Đỏ (đầy)

**Left panel (Camera)**
- Hiển thị feed camera trực tiếp
- Hiển thị mã SV quét được

**Right panel (Danh sách xe)**
- Xe đang đỗ + thời gian vào
- Sinh viên + lớp
- Click vào để xem chi tiết

---

## 🔌 API Endpoints

### **GET /health**
Kiểm tra sức khỏe server
```bash
curl http://127.0.0.1:8000/health
```

### **GET /stats**
Lấy thống kê
```bash
curl http://127.0.0.1:8000/stats
```

### **GET /parked**
Danh sách xe đang đỗ
```bash
curl http://127.0.0.1:8000/parked
```

### **POST /process-plate**
Xử lý biển số (từ ESP32)
```bash
curl -X POST \
  -F "file=@image.jpg" \
  -F "ma_sv=SV21001" \
  http://127.0.0.1:8000/process-plate
```

### **POST /register-student**
Đăng ký sinh viên (từ Laptop camera)
```bash
curl -X POST \
  http://127.0.0.1:8000/register-student?ma_sv=SV21001
```

---

## 🐛 Troubleshooting

### **Lỗi: "Cannot open camera"**
- Kiểm tra camera kết nối + quyền truy cập
- Thay `CAMERA_INDEX` trong `.env`

### **Lỗi: "Cannot connect to database"**
- Kiểm tra SQL Server đang chạy
- Xác nhận credentials trong `.env`
- Cấu hình ODBC Driver 17 for SQL Server

### **Lỗi: "zxingcpp not found"**
```bash
pip install zxing-cpp
```

### **Lỗi: "Google Vision API error"**
- Kiểm tra `key.json` tồn tại
- Xác nhận GCP project quota

---

## 📝 Database Schema

### **SinhVien** (Sinh viên)
```sql
MaSV (PK), HoTen, Khoa, Lop, SDT
```

### **Xe** (Phương tiện)
```sql
BienSo (PK), MaSV (FK), LoaiXe, MauSac, TinhTrang
```

### **TheRFID** (RFID card)
```sql
MaRFID (PK), MaSV (FK), SoDu, TinhTrang
```

### **LichSuVaoRa** (Entry/Exit log)
```sql
MaRFID, BienSo, ThoiGianVao, AnhVao, 
ThoiGianRa, AnhRa, SoTienTru, TrangThai
```

---

## 🔐 Bảo mật

- ✅ Fuzzy matching 75% ngưỡng để tránh false positive
- ✅ Kiểm tra RFID status (Khóa/Mở)
- ✅ Lưu log tất cả vào/ra
- ✅ Lưu trữ ảnh cho audit
- ✅ CORS protected API

---

## 📞 Support

Gặp vấn đề? Kiểm tra:
1. Console logs (tìm `[✗]` error)
2. Database connection
3. Camera + Google Vision credentials
4. Python version (3.10+)

---

**Made with ❤️ by Sensei - April 2026**
