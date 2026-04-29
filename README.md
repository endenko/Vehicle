# 🚗 SmartParking Valkyrie V2.0 — Hệ thống Quản lý Bãi đỗ xe Thông minh

Hệ thống quản lý bãi đỗ xe trường học sử dụng **CustomTkinter**, **SQLite**, **OpenCV**, **Google Cloud Vision OCR**, và **ESP32-CAM**.

---

## 📦 Cài đặt

### 1. Yêu cầu hệ thống

- Python 3.10+
- Camera laptop (hoặc USB webcam)
- (Tùy chọn) ESP32-CAM + IR Sensor

### 2. Cài đặt dependencies

```bash
cd TestThuGui
pip install -r requirements.txt
```

**Các thư viện chính:**

| Thư viện | Mục đích |
|----------|----------|
| `customtkinter` | GUI framework (dark/light theme) |
| `opencv-python` | Camera capture & image processing |
| `pyzbar` | Quét barcode/QR từ ảnh |
| `qrcode` | Sinh mã QR |
| `python-barcode` | Sinh mã Barcode EAN-13 |
| `thefuzz` | Fuzzy matching biển số xe |
| `google-cloud-vision` | OCR nhận diện biển số |
| `requests` | HTTP client cho ESP32/IR |
| `Pillow` | Xử lý ảnh |

### 3. Biến môi trường (.env)

```bash
cp .env.example .env
```

Cấu hình trong `.env`:

```env
# Database (mặc định dùng SQLite)
DB_BACKEND=sqlite
SQLITE_DB_PATH=./smart_parking.db

# Google Cloud Vision OCR
GOOGLE_APPLICATION_CREDENTIALS=./key.json

# ESP32 & IR Sensor (cấu hình sau)
ESP32_CAPTURE_URL=http://192.168.1.100/capture
IR_SENSOR_URL=http://192.168.1.101/trigger
ESP32_STORAGE_DIR=./static/in

# Camera
LAPTOP_CAMERA_ID=0

# Fuzzy matching
FUZZY_THRESHOLD=75
```

### 4. Google Cloud Vision

- Tải file `key.json` từ Google Cloud Console
- Đặt vào thư mục gốc `TestThuGui/key.json`
- Nếu thiếu file, hệ thống sẽ hiện thông báo lỗi (không crash)

---

## 🚀 Chạy ứng dụng

```bash
# Chạy GUI chính (+ API server)
python run.py all

# Chỉ chạy GUI
python run.py gui

# Chỉ chạy API server
python run.py api --port 8000

# Mở GUI Manager (quản lý sinh viên + sinh mã)
python run_generate.py
```

---

## 📁 Cấu trúc thư mục

```
TestThuGui/
├── run.py                      # Entry point chính (GUI + API)
├── run_generate.py             # GUI Manager (CRUD + sinh QR/Barcode)
├── smart_parking.db            # SQLite database chính
├── key.json                    # Google Cloud Vision credentials
├── requirements.txt            # Dependencies
├── schema_sqlite.sql           # Schema khởi tạo database
│
├── gui/                        # GUI chính (CustomTkinter)
│   ├── app_window.py           # Cửa sổ chính + tab navigation
│   ├── styles.py               # Design tokens & colors
│   ├── pages/
│   │   ├── xe_vao_page.py      # Tab Xe Vào
│   │   ├── xe_ra_page.py       # Tab Xe Ra (tự động hóa)
│   │   ├── dashboard_page.py   # Tab Thống kê
│   │   └── log_history_page.py # Tab Lịch sử
│   └── utils/
│       ├── camera.py           # Camera handlers (laptop + IoT)
│       └── db_local.py         # Business logic + fee calculation
│
├── createbarcode/              # Module sinh mã
│   ├── generator.py            # Sinh QR/Barcode từ dictionary
│   └── barcodes/               # Output ảnh mã
│
├── smart_parking/              # Backend package
│   ├── config.py               # Cấu hình toàn cục
│   ├── database.py             # Database manager (SQLite + SQL Server)
│   ├── vision_api.py           # FastAPI server
│   └── gui/                    # Legacy GUI components
│
├── Lich su bien so xe/         # Ảnh lịch sử
│   ├── xe_vao/                 # Ảnh xe vào
│   └── xe_ra/                  # Ảnh xe ra
│
└── static/                     # Storage cho API
    ├── in/                     # Ảnh ESP32 upload
    └── out/                    # Ảnh xử lý
```

---

## 🔄 Sơ đồ luồng hoạt động

### Luồng Xe Vào

```
┌─────────────────┐
│  Quét Barcode/QR │
└────────┬────────┘
         │
    ┌────▼────┐
    │ Tra DB  │
    └────┬────┘
         │
    ┌────▼────────────┐     ┌──────────────────────┐
    │ Tìm thấy SV?   │──NO─▶│ CTkToplevel: "Chưa   │
    └────┬────────────┘     │ đăng ký!"             │
         │ YES              └──────────────────────┘
    ┌────▼────────────┐
    │ Hiển thị info   │
    │ Chờ xác nhận    │
    └────┬────────────┘
         │
    ┌────▼────────────┐
    │ POST → IR Sensor│
    │ GET  → ESP32 📷 │
    └────┬────────────┘
         │
    ┌────▼────────────┐
    │ Lưu ảnh         │
    │ INSERT vào DB   │
    └─────────────────┘
```

### Luồng Xe Ra (Tự động)

```
┌─────────────────┐
│  Quét Barcode/QR │ ← Camera tự động quét
└────────┬────────┘
         │
    ┌────▼────────────┐
    │ Tra DB + Fuzzy  │
    │ match biển số   │
    └────┬────────────┘
         │
    ┌────▼────────────────────────────────────────┐
    │                                              │
    ▼                    ▼                    ▼
 ┌──────────┐    ┌──────────────┐    ┌──────────┐
 │ Xe KHÓA  │    │ Hết tiền     │    │ Hợp lệ   │
 │ ⛔ Nhấp   │    │ ⚠ Cảnh báo  │    │          │
 │ nháy đỏ  │    │ "Số dư không │    │          │
 │ Chặn IR  │    │  đủ"         │    │          │
 └──────────┘    └──────────────┘    └────┬─────┘
                                          │
                                     ┌────▼──────────┐
                                     │ ESP32 chụp ảnh│
                                     │ Google Vision  │
                                     │ OCR            │
                                     └────┬──────────┘
                                          │
                                ┌─────────▼─────────┐
                                │                    │
                                ▼                    ▼
                          ┌──────────┐        ┌──────────┐
                          │ ≥ 75%    │        │ < 75%    │
                          │ ✔ Mở     │        │ "Đứng im"│
                          │ barie    │        │ Re-scan  │
                          │ Trừ tiền │        │ sau 3s   │
                          └──────────┘        └──────────┘
```

---

## 💰 Biểu phí gửi xe

| Khung giờ | Phí |
|-----------|-----|
| 06:00 – 17:30 | 2,000đ |
| 17:30 – 23:00 | 3,000đ |
| 23:00 – 06:00 | ⛔ Không nhận xe |
| Gửi quá 24 giờ | +5,000đ phụ phí |

---

## 🛠 Chức năng chính

### GUI Manager (`run_generate.py`)
- CRUD sinh viên (Thêm / Sửa / Xóa)
- Sinh mã QR + Barcode tự động
- Nạp tiền vào tài khoản
- Thống kê: tổng user, tổng doanh thu

### GUI Chính (`run.py gui`)
- **Tab Xe Vào**: Camera + quét mã + xác nhận vào
- **Tab Xe Ra**: Tự động quét + fuzzy match + đối chiếu ảnh
- **Tab Log History**: Lịch sử vào/ra có filter
- **Tab Thống kê**: Dashboard real-time

### Tự động hóa
- Camera transition 3 giây giữa tab Xe Vào ↔ Xe Ra
- Auto-scan barcode → auto-process exit
- Re-scan tự động nếu biển số không khớp
- Cảnh báo đỏ nhấp nháy nếu xe bị khóa

---

## 📝 Database Schema (SQLite)

```sql
SinhVien (MaSV, HoTen, Khoa, Lop, SDT)
Xe       (BienSo, MaSV, LoaiXe, MauSac, TinhTrang)
TheRFID  (MaRFID, MaSV, SoDu, TinhTrang)
LichSuVaoRa (ID, MaRFID, BienSo, ThoiGianVao, AnhVao,
             ThoiGianRa, AnhRa, SoTienTru, TrangThai)
```

---

## 🔌 API Endpoints

```
GET  /health          → Health check
GET  /stats           → Thống kê hệ thống
GET  /parked          → Xe đang đỗ
POST /process-plate   → Xử lý biển số (ESP32)
POST /register-student → Đăng ký sinh viên (camera)
```

---

**Made with ❤️ — SmartParking Valkyrie V2.0**
