"""
Camera handler cho School Parking Management GUI.
Khôi phục và tối ưu bởi Cục An ninh Valkyrie.
"""

import base64
import os
import re
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import customtkinter as ctk
import cv2
import numpy as np
import requests
from PIL import Image

# ── Optional deps ──────────────────────────────────────────────────────────────
try:
    from pyzbar.pyzbar import decode as zbar_decode
except Exception:
    zbar_decode = None

try:
    from google.cloud import vision
except Exception:
    vision = None

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

# ── Roboflow API ────────────────────────────────────────
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "AMrcEXneFYP87Cn5lZP1")
ROBOFLOW_URL = f"https://detect.roboflow.com/vietnam-license-plate-h8t3n/1?api_key={ROBOFLOW_API_KEY}"

def _call_roboflow(frame) -> list:
    is_success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if not is_success:
        return []
    try:
        img_b64 = base64.b64encode(buffer).decode("ascii")
        resp = requests.post(
            ROBOFLOW_URL,
            data=img_b64,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=6,
        )
        if resp.status_code == 200:
            return resp.json().get("predictions", [])
    except Exception:
        pass
    return []

# ── Google Cloud Vision ─────────────────────────────────
_VISION_LOCK = threading.Lock()
_VISION_CLIENT = None
_YOLO_LOCK = threading.Lock()
_YOLO_MODEL = None

def _get_yolo_model():
    global _YOLO_MODEL
    if _YOLO_MODEL is not None: return _YOLO_MODEL
    if YOLO is None: return None
    model_path = os.getenv("YOLO_PLATE_MODEL_PATH", "ai_modules/best.pt")
    model_file = Path(model_path)
    if not model_file.exists(): return None
    with _YOLO_LOCK:
        if _YOLO_MODEL is None:
            try: _YOLO_MODEL = YOLO(str(model_file))
            except Exception: _YOLO_MODEL = None
    return _YOLO_MODEL

def _ensure_google_credential_env() -> None:
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"): return
    for candidate in [
        Path(__file__).resolve().parents[2] / "app" / "core" / "key.json",
        Path(__file__).resolve().parents[1] / "key.json",
    ]:
        if candidate.exists():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(candidate)
            return

def _get_vision_client():
    global _VISION_CLIENT
    if _VISION_CLIENT is not None: return _VISION_CLIENT
    if vision is None: return None
    _ensure_google_credential_env()
    with _VISION_LOCK:
        if _VISION_CLIENT is None:
            try: _VISION_CLIENT = vision.ImageAnnotatorClient()
            except Exception: _VISION_CLIENT = None
    return _VISION_CLIENT

# ── Text helpers ───────────────────────────────────────────────────────────────
def _normalize_plate_text(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())

def _extract_plate_candidate(raw_text: str) -> Optional[str]:
    cleaned = raw_text.upper().replace("\n", " ")
    patterns = [
        r"\b\d{2}[A-Z]\d?-?\d{3}\.?\d{2}\b",
        r"\b\d{2}[A-Z]-?\d{3,4}\b",
        r"\b\d{2}[A-Z]{1,2}\d{4,5}\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, cleaned)
        if m: return _normalize_plate_text(m.group(0))
    return None

def _extract_refc_or_qr_candidate(raw_text: str) -> Optional[str]:
    cleaned = raw_text.upper().replace("\n", " ")
    refc = re.search(r"\bREFC[-_A-Z0-9]{2,}\b", cleaned)
    if refc: return refc.group(0)
    qr_like = re.search(r"\b[A-Z0-9]{8,}\b", cleaned)
    if qr_like: return qr_like.group(0)
    return None

# ── Image save helper ──────────────────────────────────────────────────────────
_GUI_DIR = Path(__file__).resolve().parents[1]
HISTORY_DIR_NAME = "Lich su bien so xe"

def save_capture(frame: np.ndarray, subdir: str = "xe_vao") -> Optional[str]:
    save_dir = _GUI_DIR / HISTORY_DIR_NAME / subdir
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
    path = save_dir / f"bien_so_{timestamp}.jpg"
    try:
        cv2.imwrite(str(path), frame)
        return str(path)
    except Exception:
        return None

# ── Base handler ───────────────────────────────────────────────────────────────
class _BaseCameraHandler:
    def __init__(self, label: ctk.CTkLabel, on_detection: Optional[Callable[[Dict[str, object]], None]] = None, enable_plate_ocr: bool = True):
        self.label = label
        self.running = False
        self._latest_frame = None
        self._frame_lock = threading.Lock()
        self._on_detection = on_detection
        self.enable_plate_ocr = enable_plate_ocr
        self._emit_cache: Dict[str, float] = {}
        self._ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._ui_pump_running = True
        
        self._vision_interval = float(os.getenv("VISION_FRAME_INTERVAL_SECONDS", "1.4"))
        self._last_vision_ts = 0.0
        self._last_vision_plate = ""
        self._last_vision_code = ""
        self._last_plate_box: Optional[Tuple[int, int, int, int]] = None
        self._last_plate_conf = 0.0
        self._last_plate_box_ts = 0.0
        self._plate_overlay_ttl = float(os.getenv("PLATE_OVERLAY_TTL_SECONDS", "2.5"))
        
        self._roboflow_predictions: list = []
        self._roboflow_active = False
        self._roboflow_last_ts = 0.0
        self._roboflow_interval = 1.5
        
        self.last_frame_ts = 0.0
        self.label.after(50, self._pump_ui_queue)

    def stop(self):
        self.running = False
        self._ui_pump_running = False

    def get_latest_frame_base64(self, jpeg_quality: int = 85) -> Optional[str]:
        with self._frame_lock:
            if self._latest_frame is None: return None
            frame = self._latest_frame.copy()
        try:
            success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)])
            if not success: return None
            return base64.b64encode(buffer.tobytes()).decode("utf-8")
        except Exception:
            return None

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            if self._latest_frame is None: return None
            return self._latest_frame.copy()

    def _emit_detection(self, detection_type: str, value: str, confidence: float, source: str) -> None:
        value = (value or "").strip()
        if not value: return
        key = f"{detection_type}:{value}:{source}"
        now = time.time()
        if now - self._emit_cache.get(key, 0.0) < 1.4: return
        self._emit_cache[key] = now
        if callable(self._on_detection):
            self._on_detection({
                "type": detection_type,
                "value": value,
                "confidence": round(float(confidence), 2),
                "source": source,
            })

    def _draw_red_box(self, frame, x1: int, y1: int, x2: int, y2: int, text: str) -> None:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(frame, text, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2, cv2.LINE_AA)

    def _draw_top_text(self, frame, line: str, y: int) -> None:
        cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 255), 2, cv2.LINE_AA)

    def _bbox_from_vertices(self, vertices, frame_shape):
        if not vertices: return None
        points = [(int(v.x), int(v.y)) for v in vertices if getattr(v, "x", None) is not None and getattr(v, "y", None) is not None]
        if not points: return None
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        x1, y1 = max(0, min(xs)), max(0, min(ys))
        x2, y2 = min(frame_shape[1] - 1, max(xs)), min(frame_shape[0] - 1, max(ys))
        if x2 <= x1 or y2 <= y1: return None
        return (x1, y1, x2, y2)

    def _trigger_roboflow_async(self, frame) -> None:
        now = time.time()
        if self._roboflow_active or now - self._roboflow_last_ts < self._roboflow_interval: return
        self._roboflow_active = True
        self._roboflow_last_ts = now
        scan_frame = frame.copy()
        def _worker():
            self._roboflow_predictions = _call_roboflow(scan_frame)
            self._roboflow_active = False
        threading.Thread(target=_worker, daemon=True).start()

    def _enqueue_ui(self, callback: Callable[[], None]) -> None:
        if self._ui_pump_running:
            self._ui_queue.put(callback)

    def _pump_ui_queue(self) -> None:
        if not self._ui_pump_running:
            return
        try:
            while True:
                callback = self._ui_queue.get_nowait()
                try:
                    callback()
                except Exception:
                    pass
        except queue.Empty:
            pass
        try:
            self.label.after(50, self._pump_ui_queue)
        except Exception:
            self._ui_pump_running = False

    def _draw_roboflow_overlay(self, frame) -> Optional[Tuple[int,int,int,int]]:
        best_box, best_conf = None, 0.0
        for pred in self._roboflow_predictions:
            conf = float(pred.get("confidence", 0))
            cx, cy, w, h = int(pred["x"]), int(pred["y"]), int(pred["width"]), int(pred["height"])
            x1, y1 = max(0, cx - w // 2), max(0, cy - h // 2)
            x2, y2 = min(frame.shape[1], cx + w // 2), min(frame.shape[0], cy + h // 2)
            if x2 <= x1 or y2 <= y1: continue
            self._draw_red_box(frame, x1, y1, x2, y2, f"PLATE {conf*100:.1f}%")
            if conf >= 0.60 and conf > best_conf:
                best_conf, best_box = conf, (x1, y1, x2, y2)
        return best_box

    def _run_qr_refc_overlay(self, frame, emit_code: Optional[Callable[[str], None]]) -> None:
        found_any = False
        
        # Tiền xử lý đa dạng để tăng khả năng nhận diện
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 1. CLAHE (Cân bằng sáng cục bộ)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # 2. Otsu Threshold (Nhị phân hóa)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 3. Sharpening (Làm sắc nét)
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(gray, -1, kernel)

        # Danh sách các ảnh để thử quét (ưu tiên ảnh chất lượng cao nhất)
        candidates = [gray, enhanced, sharpened, thresh]

        if zbar_decode is not None:
            try:
                for img in candidates:
                    decoded = zbar_decode(img)
                    if decoded:
                        for item in decoded:
                                code = item.data.decode("utf-8", errors="ignore").strip()
                                if not code: continue
                                found_any = True
                                points = getattr(item, "polygon", None)
                                if points and len(points) >= 4:
                                    np_pts = np.array([(pt.x, pt.y) for pt in points], dtype=np.int32).reshape((-1, 1, 2))
                                    cv2.polylines(frame, [np_pts], True, (0, 0, 255), 2)
                                    x, y = int(np_pts[0][0][0]), int(np_pts[0][0][1])
                                else:
                                    rect = item.rect
                                    x, y, w, h = rect.left, rect.top, rect.width, rect.height
                                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                                # Identify REFC tokens explicitly (e.g. REFC12345) — treat them as 'refc'
                                up = code.upper()
                                if up.startswith("REFC") or "REFC" in up:
                                    dtype = "refc"
                                    display_text = up
                                else:
                                    # heuristics: JSON-like QR payloads include '{'
                                    if "{" in code or "}" in code:
                                        dtype = "qr"
                                        display_text = "SMARTPARKING"
                                    else:
                                        dtype = "barcode"
                                        display_text = code
                                cv2.putText(frame, display_text, (x, max(18, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2, cv2.LINE_AA)
                                self._emit_detection(dtype, code, 99.0, "zbar")
                                if callable(emit_code): emit_code(code)
                        if found_any: break
            except Exception: pass

        if not found_any:
            try:
                # QR Fallback
                qr_detector = cv2.QRCodeDetector()
                for img in candidates + [frame]:
                    data, bbox, _ = qr_detector.detectAndDecode(img)
                    if data:
                        data = data.strip()
                        up = data.upper()
                        if bbox is not None and len(bbox) > 0:
                            pts = np.int32(bbox).reshape(-1, 1, 2)
                            cv2.polylines(frame, [pts], True, (0, 255, 0), 2)
                            x, y = int(pts[0][0][0]), int(pts[0][0][1])
                            label = "SMARTPARKING (CV2 QR)"
                            # If the QR payload actually contains REFC token, surface it
                            if up.startswith("REFC") or "REFC" in up:
                                label = up
                            cv2.putText(frame, label, (x, max(18, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2, cv2.LINE_AA)
                        dtype = "refc" if up.startswith("REFC") or "REFC" in up else "qr"
                        self._emit_detection(dtype, data, 99.0, "cv2")
                        if callable(emit_code): emit_code(data)
                        found_any = True
                        break
            except Exception: pass

        if not found_any:
            try:
                # Barcode Fallback
                if hasattr(cv2, 'barcode'):
                    barcode_detector = cv2.barcode.BarcodeDetector()
                    for img in candidates:
                        ok, decoded_info, decoded_type, corners = barcode_detector.detectAndDecode(img)
                        if ok and decoded_info:
                            for i, bcode in enumerate(decoded_info):
                                if bcode:
                                    bcode = bcode.strip()
                                    up = bcode.upper()
                                    if corners is not None and len(corners) > i:
                                        pts = np.int32(corners[i]).reshape(-1, 1, 2)
                                        cv2.polylines(frame, [pts], True, (255, 165, 0), 2)
                                        x, y = int(pts[0][0][0]), int(pts[0][0][1])
                                        cv2.putText(frame, bcode, (x, max(18, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 165, 0), 2, cv2.LINE_AA)
                                    dtype = "refc" if up.startswith("REFC") or "REFC" in up else "barcode"
                                    self._emit_detection(dtype, bcode, 99.0, "cv2")
                                    if callable(emit_code): emit_code(bcode)
                                    found_any = True
                        if found_any: break
            except Exception: pass


    def _run_google_vision_extract(self, frame, best_box) -> None:
        self._last_vision_ts = time.time()
        client = _get_vision_client()
        if client is None: return
        
        ocr_frame = frame
        if best_box is not None:
            x1, y1, x2, y2 = best_box
            pad_x, pad_y = max(4, int((x2 - x1) * 0.15)), max(2, int((y2 - y1) * 0.10))
            x1c, y1c = max(0, x1 - pad_x), max(0, y1 - pad_y)
            x2c, y2c = min(frame.shape[1], x2 + pad_x), min(frame.shape[0], y2 + pad_y)
            ocr_frame = frame[y1c:y2c, x1c:x2c]

        try:
            ok, encoded = cv2.imencode(".jpg", ocr_frame)
            if not ok: return
            image = vision.Image(content=encoded.tobytes())
            response = client.text_detection(image=image, image_context=vision.ImageContext(language_hints=["vi"]))
            texts = response.text_annotations
            if not texts: return
            
            raw = texts[0].description
            plate_candidate = _extract_plate_candidate(raw)
            if plate_candidate:
                self._last_vision_plate = plate_candidate
                confidence = 85.0 if best_box is not None else 70.0
                self._emit_detection("plate", plate_candidate, confidence, "roboflow+vision")
                self._last_plate_box = best_box
                self._last_plate_conf = confidence
                self._last_plate_box_ts = time.time()

            refc_or_qr = _extract_refc_or_qr_candidate(raw)
            if refc_or_qr:
                self._last_vision_code = refc_or_qr
                dtype = "refc" if refc_or_qr.upper().startswith("REFC") else "qr"
                self._emit_detection(dtype, refc_or_qr, 88.0, "vision")
        except Exception:
            return

    def _show_error(self, text: str):
        def _update_ui():
            try:
                img = Image.new("RGB", (640, 360), (0, 0, 0))
                ctk_image = ctk.CTkImage(light_image=img, dark_image=img, size=(640, 360))
                self.label.configure(image=ctk_image, text=text)
            except Exception:
                pass
        self._enqueue_ui(_update_ui)

    def _render_frame(self, frame, emit_code: Optional[Callable[[str], None]] = None) -> None:
        self.last_frame_ts = time.time()
        preview = frame.copy()

        best_box = None
        
        if self.enable_plate_ocr:
            self._trigger_roboflow_async(frame)
            best_box = self._draw_roboflow_overlay(preview)
            
        self._run_qr_refc_overlay(preview, emit_code=emit_code)
        
        if self.enable_plate_ocr:
            now = time.time()
            if now - self._last_vision_ts >= self._vision_interval:
                threading.Thread(target=self._run_google_vision_extract, args=(frame, best_box), daemon=True).start()

        if self._last_vision_plate and (time.time() - self._last_plate_box_ts < self._plate_overlay_ttl):
            text = f"PLATE {self._last_plate_conf:.1f}%: {self._last_vision_plate}"
            if self._last_plate_box is not None:
                x1, y1, x2, y2 = self._last_plate_box
                self._draw_red_box(preview, x1, y1, x2, y2, text)
            else:
                self._draw_top_text(preview, text, 78)
                
        if self._last_vision_plate:
            self._draw_top_text(preview, f"PLATE: {self._last_vision_plate}", 26)
        if self._last_vision_code:
            self._draw_top_text(preview, f"CODE: {self._last_vision_code}", 52)

        with self._frame_lock:
            self._latest_frame = preview.copy()

        rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)

        def _update_ui():
            try:
                width = max(int(self.label.winfo_width() or 640), 320)
                height = max(int(self.label.winfo_height() or 300), 180)
                resized = pil_image.resize((width, height))
                ctk_image = ctk.CTkImage(light_image=resized, dark_image=resized, size=(width, height))
                self.label.configure(image=ctk_image, text="")
            except Exception:
                pass

        self._enqueue_ui(_update_ui)

# ── Laptop / webcam handler ────────────────────────────────────────────────────
class CameraHandler:
    def __init__(self, label: ctk.CTkLabel, on_detection=None, callback=None):
        self.base = _BaseCameraHandler(label, on_detection=on_detection, enable_plate_ocr=False)
        self.callback = callback
        self.cap = None

    def start(self, camera_id: int = 0):
        if self.base.running: return
        self.base.running = True
        if not self.base._ui_pump_running:
            self.base._ui_pump_running = True
            self.base.label.after(50, self.base._pump_ui_queue)
        
        def _init_and_run():
            self.cap = cv2.VideoCapture(camera_id)
            if not self.cap.isOpened():
                self.base._show_error("Không mở được camera laptop")
                self.base.running = False
                return
            self._update()
            
        threading.Thread(target=_init_and_run, daemon=True).start()

    def stop(self):
        self.base.stop()
        if self.cap: self.cap.release()

    def get_latest_frame_base64(self, jpeg_quality: int = 85) -> Optional[str]:
        return self.base.get_latest_frame_base64(jpeg_quality=jpeg_quality)

    def get_latest_frame(self) -> Optional[np.ndarray]:
        return self.base.get_latest_frame()

    def _emit_code(self, code: str) -> None:
        if callable(self.callback):
            self.callback(code)

    def _update(self):
        while self.base.running:
            if self.cap is None: break
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            self.base._render_frame(frame, emit_code=self._emit_code)
        self.base._show_error("Camera đã đóng")

# ── ESP32 IoT Camera ───────────────────────────────────────────────────────────
class IoTCameraHandler:
    def __init__(self, label: ctk.CTkLabel, capture_url: Optional[str] = None, on_detection=None):
        self.base = _BaseCameraHandler(label, on_detection=on_detection, enable_plate_ocr=True)
        self.capture_url = capture_url
        # Mặc định là thư mục static/in nơi API (vision_api.py) lưu ảnh từ ESP32
        default_storage = Path(__file__).resolve().parents[2] / "static" / "in"
        storage_dir = os.getenv("ESP32_STORAGE_DIR", str(default_storage))
        self.storage_dir = Path(storage_dir)
        self.poll_interval = float(os.getenv("ESP32_REFRESH_SECONDS", "1.0"))
        self._last_file: Optional[str] = None

    def start(self):
        if self.base.running: return
        self.base.running = True
        if not self.base._ui_pump_running:
            self.base._ui_pump_running = True
            self.base.label.after(50, self.base._pump_ui_queue)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._update, daemon=True).start()

    def stop(self):
        self.base.stop()

    def get_latest_frame_base64(self, jpeg_quality: int = 85) -> Optional[str]:
        return self.base.get_latest_frame_base64(jpeg_quality=jpeg_quality)

    def get_latest_frame(self) -> Optional[np.ndarray]:
        return self.base.get_latest_frame()

    def _get_latest_image_path(self) -> Optional[Path]:
        try:
            files = sorted(self.storage_dir.glob("*.jpg"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files: return files[0]
        except Exception: pass
        return None

    def _update(self):
        while self.base.running:
            try:
                latest = self._get_latest_image_path()
                if latest is None:
                    self.base._show_error("Chờ ảnh từ ESP32 camera IoT...")
                    time.sleep(self.poll_interval)
                    continue

                current_name = str(latest)
                if current_name != self._last_file:
                    self._last_file = current_name
                    frame = cv2.imread(current_name)
                    if frame is not None:
                        self.base._render_frame(frame)
                time.sleep(self.poll_interval)
            except Exception:
                self.base._show_error("Lỗi đọc ảnh IoT camera")
                time.sleep(self.poll_interval)