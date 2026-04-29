"""
gui/utils/hardware.py
Utility cho việc tương tác với phần cứng (IR Sensor, ESP32-CAM, Barrier).
Hỗ trợ chế độ MOCK để test không cần thiết bị thật.
"""
import requests
import threading
from smart_parking.config import (
    URL_IR_SENSOR_IN, URL_IR_SENSOR_OUT,
    URL_ESP32_CAPTURE_IN, URL_ESP32_CAPTURE_OUT,
    URL_BARRIER_OPEN, MOCK_HARDWARE
)

def trigger_ir_sensor(direction="in", timeout=3):
    """Giả lập/Thực tế kích hoạt cảm biến IR"""
    url = URL_IR_SENSOR_IN if direction == "in" else URL_IR_SENSOR_OUT
    if MOCK_HARDWARE:
        print(f"[MOCK] Kích hoạt cảm biến IR ({direction}) -> OK")
        return True
    try:
        resp = requests.post(url, timeout=timeout)
        return resp.status_code == 200
    except Exception as e:
        print(f"[!] Lỗi IR Sensor ({direction}): {e}")
        return False

def request_esp32_capture(direction="in", timeout=5):
    """Giả lập/Thực tế yêu cầu ESP32 chụp ảnh"""
    url = URL_ESP32_CAPTURE_IN if direction == "in" else URL_ESP32_CAPTURE_OUT
    if MOCK_HARDWARE:
        print(f"[MOCK] Yêu cầu ESP32 chụp ảnh ({direction}) -> OK")
        return True
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code == 200
    except Exception as e:
        print(f"[!] Lỗi ESP32 Capture ({direction}): {e}")
        return False

def open_barrier(timeout=3):
    """Giả lập/Thực tế mở Barie"""
    if MOCK_HARDWARE:
        print("[MOCK] Mở Barie -> OK")
        return True
    try:
        resp = requests.post(URL_BARRIER_OPEN, timeout=timeout)
        return resp.status_code == 200
    except Exception as e:
        print(f"[!] Lỗi mở Barie: {e}")
        return False
