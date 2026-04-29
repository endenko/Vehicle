#!/usr/bin/env python
"""
run_gui.py — Entry point cho School Parking Management GUI
Chạy: python run_gui.py
"""
import sys
from pathlib import Path

# Đảm bảo thư mục gốc trong sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Tạo thư mục lưu ảnh
for sub in ["xe_vao", "xe_ra", "esp32_inbox"]:
    (BASE_DIR / "Lich su bien so xe" / sub).mkdir(parents=True, exist_ok=True)

from gui.app_window import MainApp  # noqa: E402

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
