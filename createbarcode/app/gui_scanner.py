from __future__ import annotations

import importlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import cv2
import requests
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import ttk

from app.database import (
    bootstrap_database,
    get_student_by_id,
    get_student_by_product_code,
    get_student_by_ref_code,
)
from app.qr_generator import generate_all_barcodes, generate_all_qr


@dataclass
class DetectionSnapshot:
    detections: List[Dict[str, Any]] = field(default_factory=list)
    target: Optional[Dict[str, Any]] = None
    error_message: str = ""


class CameraScannerApp:
    def __init__(
        self,
        root: tk.Tk,
        api_url: str,
        detect_interval_seconds: float = 3.0,
        qr_interval_seconds: float = 3.0,
        camera_index: int = 0,
    ) -> None:
        self.root = root
        self.api_url = api_url
        self.detect_interval_seconds = detect_interval_seconds
        self.qr_interval_seconds = qr_interval_seconds

        self.capture = cv2.VideoCapture(camera_index)
        if not self.capture.isOpened():
            raise RuntimeError("Cannot open laptop camera")

        bootstrap_database(reset=False)
        generate_all_qr()
        generate_all_barcodes()

        self.state_lock = threading.Lock()
        self.snapshot = DetectionSnapshot()
        self.qr_detector = cv2.QRCodeDetector()
        self.zxingcpp = None
        try:
            self.zxingcpp = importlib.import_module("zxingcpp")
        except ModuleNotFoundError:
            self.zxingcpp = None
        self.barcode_detector = cv2.barcode_BarcodeDetector() if hasattr(cv2, "barcode_BarcodeDetector") else None

        self.api_inflight = False
        self.last_api_call = 0.0
        self.last_qr_processed = 0.0
        self.running = True

        self.video_label: ttk.Label
        self.status_var = tk.StringVar(value="Camera ready. Waiting for scan...")
        self.student_id_var = tk.StringVar(value="-")
        self.full_name_var = tk.StringVar(value="-")
        self.class_var = tk.StringVar(value="-")
        self.major_var = tk.StringVar(value="-")
        self.email_var = tk.StringVar(value="-")
        self.phone_var = tk.StringVar(value="-")
        self.ref_code_var = tk.StringVar(value="-")
        self.product_code_var = tk.StringVar(value="-")
        self.code_type_var = tk.StringVar(value="-")
        self.raw_code_var = tk.StringVar(value="-")

        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._update_loop()

    def _build_ui(self) -> None:
        self.root.title("YOLOv8 API + Student QR + Product Barcode Scanner")
        self.root.geometry("1180x700")

        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        main_frame.columnconfigure(0, weight=3)
        main_frame.columnconfigure(1, weight=2)
        main_frame.rowconfigure(0, weight=1)

        video_frame = ttk.LabelFrame(main_frame, text="Live Camera")
        video_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        video_frame.columnconfigure(0, weight=1)
        video_frame.rowconfigure(0, weight=1)

        self.video_label = ttk.Label(video_frame)
        self.video_label.grid(row=0, column=0, sticky="nsew")

        info_frame = ttk.LabelFrame(main_frame, text="Scan Result")
        info_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        info_frame.columnconfigure(1, weight=1)

        fields = [
            ("Status", self.status_var),
            ("Student ID", self.student_id_var),
            ("Full Name", self.full_name_var),
            ("Class", self.class_var),
            ("Major", self.major_var),
            ("Email", self.email_var),
            ("Phone", self.phone_var),
            ("REFC", self.ref_code_var),
            ("Product Code", self.product_code_var),
            ("Code Type", self.code_type_var),
            ("Raw Code", self.raw_code_var),
        ]

        for row, (label, value_var) in enumerate(fields):
            ttk.Label(info_frame, text=f"{label}:").grid(
                row=row,
                column=0,
                sticky="nw",
                padx=(10, 6),
                pady=6,
            )
            ttk.Label(
                info_frame,
                textvariable=value_var,
                wraplength=360,
                justify=tk.LEFT,
            ).grid(row=row, column=1, sticky="nw", padx=(0, 10), pady=6)

        hint = (
            "Flow: API YOLO runs every 3s for target lock. "
            "QR/barcode scan also auto every 3s. "
            "Red line in center = aim line."
        )
        ttk.Label(info_frame, text=hint, wraplength=420, justify=tk.LEFT).grid(
            row=len(fields),
            column=0,
            columnspan=2,
            sticky="w",
            padx=10,
            pady=(10, 8),
        )

    def _update_loop(self) -> None:
        if not self.running:
            return

        ok, frame = self.capture.read()
        if not ok:
            self.status_var.set("Cannot read frame from camera")
            self.root.after(30, self._update_loop)
            return

        now = time.time()
        if (not self.api_inflight) and (now - self.last_api_call >= self.detect_interval_seconds):
            self.last_api_call = now
            self.api_inflight = True
            frame_for_api = frame.copy()
            worker = threading.Thread(target=self._call_detection_api, args=(frame_for_api,), daemon=True)
            worker.start()

        self._process_code(frame, now)
        display_frame = self._draw_overlay(frame)
        self._render_frame(display_frame)

        self.root.after(30, self._update_loop)

    def _call_detection_api(self, frame: Any) -> None:
        try:
            success, buffer = cv2.imencode(".jpg", frame)
            if not success:
                raise RuntimeError("Cannot encode frame for API")

            response = requests.post(
                self.api_url,
                files={"file": ("frame.jpg", buffer.tobytes(), "image/jpeg")},
                timeout=8,
            )
            response.raise_for_status()
            payload = response.json()

            with self.state_lock:
                self.snapshot.detections = payload.get("detections", [])
                self.snapshot.target = payload.get("target")
                self.snapshot.error_message = ""
        except Exception as error:
            with self.state_lock:
                self.snapshot.error_message = str(error)
        finally:
            self.api_inflight = False

    def _process_code(self, frame: Any, now: float) -> None:
        decoded = self._detect_any_code(frame)
        if decoded is None:
            return

        if now - self.last_qr_processed < self.qr_interval_seconds:
            return

        decoded_text, code_type = decoded
        self.last_qr_processed = now
        self.raw_code_var.set(decoded_text)
        self.code_type_var.set(code_type)

        student = self._resolve_student(decoded_text)
        if student is None:
            self.status_var.set("Code detected but student not found in database")
            self._clear_student_vars()
            return

        self.student_id_var.set(student.get("student_id", "-"))
        self.full_name_var.set(student.get("full_name", "-"))
        self.class_var.set(student.get("class_name", "-"))
        self.major_var.set(student.get("major", "-"))
        self.email_var.set(student.get("email", "-"))
        self.phone_var.set(student.get("phone", "-"))
        self.ref_code_var.set(student.get("ref_code", "-"))
        self.product_code_var.set(student.get("product_code", "-"))
        self.status_var.set(f"Scan success ({code_type})")

    def _detect_any_code(self, frame: Any) -> Optional[tuple[str, str]]:
        qr_text, _, _ = self.qr_detector.detectAndDecode(frame)
        if qr_text:
            return qr_text, "QR"

        if self.zxingcpp is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            results = self.zxingcpp.read_barcodes(gray)
            for result in results:
                text = str(getattr(result, "text", "")).strip()
                if not text:
                    continue
                code_type = str(getattr(result, "format", "BARCODE")).strip() or "BARCODE"
                return text, code_type

        if self.barcode_detector is None:
            return None

        try:
            ok, decoded_infos, decoded_types, _ = self.barcode_detector.detectAndDecodeWithType(frame)
        except Exception:
            return None

        if not ok:
            return None

        for index, info in enumerate(decoded_infos):
            text = str(info).strip()
            if not text:
                continue

            code_type = "BARCODE"
            if index < len(decoded_types):
                decoded_type = str(decoded_types[index]).strip()
                if decoded_type:
                    code_type = decoded_type

            return text, code_type

        return None

    def _resolve_student(self, decoded_text: str) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {}
        normalized_text = decoded_text
        try:
            parsed_payload: Any = json.loads(decoded_text)
            if isinstance(parsed_payload, dict):
                payload = parsed_payload
            elif isinstance(parsed_payload, (str, int, float)):
                normalized_text = str(parsed_payload)
        except json.JSONDecodeError:
            payload = {}

        student_id = str(payload.get("student_id", "")).strip().upper()
        ref_code = str(payload.get("ref_code", "")).strip().upper()
        product_code = re.sub(r"\D", "", str(payload.get("product_code", "")))

        token = normalized_text.strip().upper()
        token_digits = re.sub(r"\D", "", token)
        if not student_id and not ref_code and not product_code:
            if token.startswith("REFC-"):
                ref_code = token
            elif token.startswith("SV"):
                student_id = token
            elif len(token_digits) in {12, 13}:
                product_code = token_digits
            else:
                student_id = token

        if student_id:
            student = get_student_by_id(student_id)
            if student is not None:
                return student

        if ref_code:
            student = get_student_by_ref_code(ref_code)
            if student is not None:
                return student

        if product_code:
            student = get_student_by_product_code(product_code)
            if student is not None:
                return student

        return None

    def _clear_student_vars(self) -> None:
        self.student_id_var.set("-")
        self.full_name_var.set("-")
        self.class_var.set("-")
        self.major_var.set("-")
        self.email_var.set("-")
        self.phone_var.set("-")
        self.ref_code_var.set("-")
        self.product_code_var.set("-")

    def _draw_overlay(self, frame: Any) -> Any:
        height, width = frame.shape[:2]
        center_x = width // 2

        cv2.line(frame, (center_x, 0), (center_x, height), (0, 0, 255), 2)
        cv2.putText(
            frame,
            "MUC TIEU",
            (center_x + 10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )

        with self.state_lock:
            detections = list(self.snapshot.detections)
            target = dict(self.snapshot.target) if self.snapshot.target else None
            api_error = self.snapshot.error_message

        for detection in detections:
            x1 = int(detection.get("x1", 0))
            y1 = int(detection.get("y1", 0))
            x2 = int(detection.get("x2", 0))
            y2 = int(detection.get("y2", 0))
            class_name = str(detection.get("class_name", "obj"))
            conf = float(detection.get("confidence", 0.0))
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 215, 255), 1)
            cv2.putText(
                frame,
                f"{class_name} {conf:.2f}",
                (x1, max(18, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 215, 255),
                1,
            )

        if target:
            tx1 = int(target.get("x1", 0))
            ty1 = int(target.get("y1", 0))
            tx2 = int(target.get("x2", 0))
            ty2 = int(target.get("y2", 0))
            tname = str(target.get("class_name", "target"))
            cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), (0, 0, 255), 2)
            cv2.putText(
                frame,
                f"LOCK: {tname}",
                (tx1, max(18, ty1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 255),
                2,
            )

        if api_error:
            cv2.putText(
                frame,
                f"API ERROR: {api_error[:70]}",
                (10, max(20, height - 14)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 255),
                1,
            )

        return frame

    def _render_frame(self, frame: Any) -> None:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb_frame)
        image = image.resize((760, 520), Image.Resampling.LANCZOS)

        tk_image = ImageTk.PhotoImage(image=image)
        self.video_label.imgtk = tk_image
        self.video_label.configure(image=tk_image)

    def on_close(self) -> None:
        self.running = False
        if self.capture.isOpened():
            self.capture.release()
        self.root.destroy()


def run_gui(
    api_url: str = "http://127.0.0.1:8000/detect",
    detect_interval_seconds: float = 3.0,
    qr_interval_seconds: float = 3.0,
    camera_index: int = 0,
) -> None:
    root = tk.Tk()
    app = CameraScannerApp(
        root,
        api_url=api_url,
        detect_interval_seconds=detect_interval_seconds,
        qr_interval_seconds=qr_interval_seconds,
        camera_index=camera_index,
    )
    root.mainloop()


if __name__ == "__main__":
    run_gui()
