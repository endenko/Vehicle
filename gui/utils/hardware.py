"""
gui/utils/hardware.py
Utility cho việc tương tác với phần cứng (IR Sensor, ESP32-CAM, Barrier).
- Phiên bản async (httpx) cho FastAPI server.
- Phiên bản sync wrapper cho GUI (Tkinter thread).
- Hỗ trợ chế độ MOCK khi MOCK_HARDWARE=yes trong .env.

⚠️ TUYỆT ĐỐI KHÔNG DÙNG time.sleep() — dùng httpx async hoặc timeout.
"""
import asyncio
import httpx

from smart_parking.config import (
    ESP32_IP,
    URL_IR_SENSOR_IN, URL_IR_SENSOR_OUT,
    URL_ESP32_CAPTURE_IN, URL_ESP32_CAPTURE_OUT,
    URL_BARRIER_OPEN, MOCK_HARDWARE
)


# ══════════════════════════════════════════════════════════════
# ASYNC FUNCTIONS (Dùng trong FastAPI — await trực tiếp)
# ══════════════════════════════════════════════════════════════

async def open_barrier(timeout: float = 3.0) -> bool:
    """Mở barie qua ESP32 (async, non-blocking)."""
    if MOCK_HARDWARE:
        print("[MOCK] Mở Barie -> OK")
        return True
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(URL_BARRIER_OPEN, timeout=timeout)
            print(f"[✓] Mở Barie -> {resp.status_code}")
            return resp.status_code == 200
    except httpx.TimeoutException:
        print(f"[!] Timeout mở Barie ({timeout}s)")
        return False
    except Exception as e:
        print(f"[!] Lỗi mở Barie: {e}")
        return False


async def trigger_ir_sensor_async(direction: str = "in", timeout: float = 3.0) -> bool:
    """Kích hoạt cảm biến IR (async)."""
    url = URL_IR_SENSOR_IN if direction == "in" else URL_IR_SENSOR_OUT
    if MOCK_HARDWARE:
        print(f"[MOCK] Kích hoạt cảm biến IR ({direction}) -> OK")
        return True
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, timeout=timeout)
            return resp.status_code == 200
    except Exception as e:
        print(f"[!] Lỗi IR Sensor ({direction}): {e}")
        return False


async def request_esp32_capture_async(direction: str = "in", timeout: float = 5.0) -> bool:
    """Yêu cầu ESP32 chụp ảnh (async)."""
    url = URL_ESP32_CAPTURE_IN if direction == "in" else URL_ESP32_CAPTURE_OUT
    if MOCK_HARDWARE:
        print(f"[MOCK] Yêu cầu ESP32 chụp ảnh ({direction}) -> OK")
        return True
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=timeout)
            return resp.status_code == 200
    except Exception as e:
        print(f"[!] Lỗi ESP32 Capture ({direction}): {e}")
        return False


# ══════════════════════════════════════════════════════════════
# SYNC WRAPPERS (Dùng trong GUI Tkinter thread — KHÔNG blocking main)
# ══════════════════════════════════════════════════════════════

def _run_async(coro):
    """Chạy coroutine từ synchronous context (threading)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Đang trong event loop (vd: FastAPI) → không thể dùng asyncio.run()
            # Tạo loop mới trong thread riêng
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=10)
        else:
            return asyncio.run(coro)
    except RuntimeError:
        return asyncio.run(coro)


def trigger_ir_sensor(direction: str = "in", timeout: float = 3.0) -> bool:
    """Sync wrapper: Kích hoạt cảm biến IR."""
    return _run_async(trigger_ir_sensor_async(direction, timeout))


def request_esp32_capture(direction: str = "in", timeout: float = 5.0) -> bool:
    """Sync wrapper: Yêu cầu ESP32 chụp ảnh."""
    return _run_async(request_esp32_capture_async(direction, timeout))


def open_barrier_sync(timeout: float = 3.0) -> bool:
    """Sync wrapper: Mở barie (dùng trong GUI thread)."""
    return _run_async(open_barrier(timeout))


# ══════════════════════════════════════════════════════════════
# KIỂM TRA IR SENSOR (Phát hiện xe trước khi xử lý)
# ══════════════════════════════════════════════════════════════

async def check_ir_sensor_async(direction: str = "in", timeout: float = 3.0) -> bool:
    """Kiểm tra IR sensor: có xe đang chắn không? (async).
    
    Returns:
        True nếu IR phát hiện có xe (bị chắn)
        False nếu không có xe (IR tự do)
    """
    url = URL_IR_SENSOR_IN if direction == "in" else URL_IR_SENSOR_OUT
    if MOCK_HARDWARE:
        print(f"[MOCK] IR Sensor ({direction}) → Có xe")
        return True
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                # ESP32 trả về {"detected": true/false} hoặc status code
                detected = data.get("detected", data.get("ir", True))
                print(f"[🔍] IR Sensor ({direction}) → {'Có xe' if detected else 'Không có xe'}")
                return bool(detected)
            return False
    except Exception as e:
        print(f"[!] Lỗi kiểm tra IR Sensor ({direction}): {e}")
        return False


def check_ir_sensor(direction: str = "in", timeout: float = 3.0) -> bool:
    """Sync wrapper: Kiểm tra IR sensor có xe không."""
    return _run_async(check_ir_sensor_async(direction, timeout))
