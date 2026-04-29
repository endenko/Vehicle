"""
SmartParking Valkyrie - Entry Point Chính
Khởi động API Server + GUI Application
"""
import argparse
import sys
import subprocess
import threading
import time
from pathlib import Path

def run_api_server(host: str, port: int):
    """Chạy API server trong thread riêng"""
    from smart_parking.vision_api import run_api_server
    print(f"[→] Khởi động API server tại http://{host}:{port}", flush=True)
    run_api_server(host=host, port=port)

def run_gui_app():
    """Chạy ứng dụng GUI mới"""
    from gui.app_window import MainApp
    print("[→] Khởi động GUI ứng dụng mới", flush=True)
    app = MainApp()
    app.mainloop()

def main():
    parser = argparse.ArgumentParser(
        description="SmartParking Valkyrie - Hệ thống quản lý bãi đỗ xe thông minh"
    )
    
    parser.add_argument(
        "mode",
        choices=["api", "gui", "all"],
        default="all",
        nargs="?",
        help="Mode chạy: api (chỉ server), gui (chỉ giao diện), all (cả hai)"
    )
    
    parser.add_argument("--host", default="127.0.0.1", help="API server host")
    parser.add_argument("--port", type=int, default=8000, help="API server port")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔐 CỤC CẢNH SÁT VALKYRIE - TRẠM KIỂM SOÁT BÃI ĐỖ XE")
    print("=" * 60)
    
    if args.mode == "api":
        run_api_server(args.host, args.port)
    
    elif args.mode == "gui":
        run_gui_app()
    
    elif args.mode == "all":
        # Chạy API server trong thread riêng
        api_thread = threading.Thread(
            target=run_api_server,
            args=(args.host, args.port),
            daemon=True
        )
        api_thread.start()
        
        # Đợi API sẵn sàng
        time.sleep(2)
        
        # Chạy GUI ứng dụng
        run_gui_app()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[✓] Ứng dụng dừng lại")
        sys.exit(0)
    except Exception as e:
        print(f"\n[✗] Lỗi: {e}")
        sys.exit(1)
