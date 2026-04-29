"""
Cấu hình toàn cục cho SmartParking Valkyrie
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ============================================================
# ĐƯỜNG DẪN & THÀNH PHỐ VĂN BẢN
# ============================================================
BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")
STORAGE_DIR = BASE_DIR / "static"
STORAGE_IN = STORAGE_DIR / "in"
STORAGE_OUT = STORAGE_DIR / "out"
STORAGE_TMP = STORAGE_DIR / "tmp"

# Đảm bảo các thư mục tồn tại
for dir_path in [STORAGE_DIR, STORAGE_IN, STORAGE_OUT, STORAGE_TMP]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ============================================================
# THƯ MỤC LƯU BẰNG CHỨNG (THEO YÊU CẦU)
# ============================================================
EVIDENCE_DIR = BASE_DIR / "Lịch sử biển số xe"
EVIDENCE_IN_DIR = EVIDENCE_DIR / "vao"
EVIDENCE_OUT_DIR = EVIDENCE_DIR / "ra"
ESP32_INBOX_DIR = EVIDENCE_DIR / "esp32_inbox"

for dir_path in [EVIDENCE_DIR, EVIDENCE_IN_DIR, EVIDENCE_OUT_DIR, ESP32_INBOX_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ============================================================
# CẤU HÌNH DATABASE
# ============================================================
DB_BACKEND = os.getenv('DB_BACKEND', 'auto').lower()
SQLITE_DB_PATH = Path(os.getenv('SQLITE_DB_PATH', str(BASE_DIR / "smart_parking.db")))
SQLITE_SCHEMA_PATH = BASE_DIR / "schema_sqlite.sql"

DB_CONFIG = {
    'DRIVER': '{ODBC Driver 17 for SQL Server}',
    'SERVER': os.getenv('DB_SERVER', 'localhost'),
    'DATABASE': os.getenv('DB_NAME', 'SmartParking_Valkyrie'),
    'UID': os.getenv('DB_USER', 'sa'),
    'PWD': os.getenv('DB_PASSWORD', ''),
    'TRUSTED_CONNECTION': os.getenv('DB_TRUSTED_CONNECTION', 'no').lower() == 'yes'
}

# ============================================================
# CẤU HÌNH GOOGLE CLOUD VISION
# ============================================================
GOOGLE_CREDENTIALS_PATH = BASE_DIR / "key.json"
if GOOGLE_CREDENTIALS_PATH.exists():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(GOOGLE_CREDENTIALS_PATH)

# ============================================================
# CẤU HÌNH ROBOFLOW (Nếu dùng YOLO trên ESP32)
# ============================================================
ROBOFLOW_API_KEY = os.getenv('ROBOFLOW_API_KEY', '')
ROBOFLOW_MODEL = "vietnam-license-plate-h8t3n"
ROBOFLOW_VERSION = 1

# ============================================================
# CẤU HÌNH API SERVER
# ============================================================
API_HOST = os.getenv('API_HOST', '127.0.0.1')
API_PORT = int(os.getenv('API_PORT', 8000))
API_ENDPOINT = f"http://{API_HOST}:{API_PORT}"

# ============================================================
# CẤU HÌNH CAMERA
# ============================================================
CAMERA_INDEX = int(os.getenv('CAMERA_INDEX', 0))
CAMERA_FRAME_WIDTH = 640
CAMERA_FRAME_HEIGHT = 480
CAMERA_FPS = 30

# ============================================================
# CẤU HÌNH FUZZY MATCHING
# ============================================================
FUZZY_THRESHOLD = int(os.getenv('FUZZY_THRESHOLD', 75))  # Ngưỡng 75%
MIN_BALANCE_REQUIRED = int(os.getenv('MIN_BALANCE_REQUIRED', 3000))
EMPTY_FRAMES_THRESHOLD = 30  # Số frame trống để reset
DETECTION_INTERVAL = 3.0  # Giây
QR_INTERVAL = 3.0  # Giây

# ============================================================
# CẤU HÌNH GUI
# ============================================================
GUI_TITLE = "Cục Cảnh sát Valkyrie - Trạm Kiểm soát Bãi Đỗ Xe Thông Minh V2.0"
GUI_WIDTH = 1400
GUI_HEIGHT = 850
GUI_BG_COLOR = "#2c3e50"
GUI_HEADER_COLOR = "#34495e"

# ============================================================
# CẤU HÌNH LOGGING
# ============================================================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = BASE_DIR / "smart_parking.log"

# ============================================================
# CẤU HÌNH THÔNG BÁO
# ============================================================
NOTIFY_SUCCESS = "🟢 CHẤP NHẬN"
NOTIFY_REJECTION = "🔴 TỪ CHỐI"
NOTIFY_WARNING = "🟡 CẢNH BÁO"
NOTIFY_ERROR = "⛔ LỖI"
