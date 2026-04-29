"""
Test Script - Kiểm tra các component chính của hệ thống
"""
import sys
from pathlib import Path

def test_imports():
    """Kiểm tra imports"""
    print("[TEST] Kiểm tra imports...")
    
    try:
        from smart_parking.config import DB_CONFIG
        print("  ✓ config.py")
    except Exception as e:
        print(f"  ✗ config.py: {e}")
    
    try:
        from smart_parking.database import db_manager
        print("  ✓ database.py")
    except Exception as e:
        print(f"  ✗ database.py: {e}")
    
    try:
        from smart_parking.fuzzy_auth import authenticate_with_ocr
        print("  ✓ fuzzy_auth.py")
    except Exception as e:
        print(f"  ✗ fuzzy_auth.py: {e}")
    
    try:
        from smart_parking.camera_scanner import CameraScanner
        print("  ✓ camera_scanner.py")
    except Exception as e:
        print(f"  ✗ camera_scanner.py: {e}")
    
    try:
        from smart_parking.gui.dashboard import StatisticsDashboard
        print("  ✓ gui/dashboard.py")
    except Exception as e:
        print(f"  ✗ gui/dashboard.py: {e}")
    
    try:
        from smart_parking.gui.main_window import SmartParkingMainWindow
        print("  ✓ gui/main_window.py")
    except Exception as e:
        print(f"  ✗ gui/main_window.py: {e}")
    
    print()

def test_database():
    """Kiểm tra kết nối database"""
    print("[TEST] Kiểm tra database...")
    
    try:
        from smart_parking.database import db_manager
        if db_manager.connect():
            print("  ✓ Kết nối database thành công")
            
            # Test query
            stats = db_manager.get_statistics()
            print(f"  ✓ Thống kê: {stats}")
            
            db_manager.disconnect()
        else:
            print("  ✗ Lỗi kết nối database")
    except Exception as e:
        print(f"  ✗ Lỗi: {e}")
    
    print()

def test_camera():
    """Kiểm tra camera"""
    print("[TEST] Kiểm tra camera...")
    
    try:
        from smart_parking.camera_scanner import CameraScanner
        scanner = CameraScanner(camera_index=0)
        
        ret, frame = scanner.read_frame()
        if ret:
            print("  ✓ Camera sẵn sàng")
            scanner.release()
        else:
            print("  ✗ Không thể đọc frame từ camera")
    except Exception as e:
        print(f"  ✗ Lỗi: {e}")
    
    print()

if __name__ == "__main__":
    print("=" * 60)
    print("SmartParking Valkyrie - TEST SUITE")
    print("=" * 60)
    print()
    
    test_imports()
    
    if "--db" in sys.argv:
        test_database()
    
    if "--camera" in sys.argv:
        test_camera()
    
    print("[✓] Test hoàn thành")
