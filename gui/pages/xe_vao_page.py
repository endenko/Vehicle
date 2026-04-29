# gui/pages/xe_vao_page.py
"""
Tab Xe Vào — Redesigned:
- Camera laptop + IoT (trái)
- Form xử lý + Treeview xe đang đỗ (phải)
- Xóa Lane ComboBox
- Layout đồng bộ với Xe Ra
- Treeview thay cho textbox
"""
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import ttk

import customtkinter as ctk
import cv2
from PIL import Image

try:
    from pyzbar.pyzbar import decode as zbar_decode
except ImportError:
    zbar_decode = None

if (__package__ or "").startswith("gui"):
    from ..styles import AppStyle
    from ..utils.camera import CameraHandler, IoTCameraHandler, save_capture
    from ..utils.db_local import lookup_by_barcode, process_entry, get_active
else:
    from gui.styles import AppStyle
    from gui.utils.camera import CameraHandler, IoTCameraHandler, save_capture
    from gui.utils.db_local import lookup_by_barcode, process_entry, get_active


class XeVaoPage(ctk.CTkFrame):
    def __init__(self, parent, main_app, on_transaction_updated=None):
        super().__init__(parent, fg_color="transparent")
        self.main_app = main_app
        self.on_updated = on_transaction_updated
        self._transition_job = None
        self._transition_remaining = 0
        self._transition_done = None
        self._active_popup = None

        self.grid_columnconfigure(0, weight=5)
        self.grid_columnconfigure(1, weight=4)
        self.grid_rowconfigure(0, weight=1)

        self._build_cam_panel()
        self._build_right_panel()
        # Chờ 2s mới tải danh sách xe đang đỗ
        self.after(2000, self._refresh_active_list)

    # ── Camera panel (trái) ───────────────────────────────────────────────────
    def _build_cam_panel(self):
        p = ctk.CTkFrame(self, fg_color=AppStyle.CARD_BG, corner_radius=14)
        p.grid(row=0, column=0, padx=(8, 5), pady=8, sticky="nsew")

        ctk.CTkLabel(
            p, text="📷  Camera Giám Sát — Xe Vào",
            font=AppStyle.SUBTITLE_FONT, text_color=AppStyle.PRIMARY
        ).pack(anchor="w", padx=14, pady=(14, 4))

        ctk.CTkLabel(
            p, text="Laptop camera  (barcode · QR · REFC · biển số)",
            font=AppStyle.SMALL_FONT, text_color=AppStyle.TEXT_SECONDARY
        ).pack(anchor="w", padx=14)

        self.lbl_local = ctk.CTkLabel(
            p, text="Camera đang chờ...", fg_color="#0F172A", height=220,
            corner_radius=10, text_color=AppStyle.TEXT_MUTED
        )
        self.lbl_local.pack(fill="x", padx=14, pady=(4, 8))

        # Nút quét từ thư mục
        tf = ctk.CTkFrame(p, fg_color="transparent")
        tf.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkButton(
            tf, text="📂 Quét từ thư mục (TestCamera)",
            command=self._scan_from_test_folder,
            fg_color=AppStyle.SUCCESS, height=32, font=AppStyle.SMALL_FONT
        ).pack(side="left")

        ctk.CTkLabel(
            p, text="IoT ESP32 camera  (ảnh từ inbox thư mục)",
            font=AppStyle.SMALL_FONT, text_color=AppStyle.TEXT_SECONDARY
        ).pack(anchor="w", padx=14)

        self.lbl_iot = ctk.CTkLabel(
            p, text="Camera IoT đang chờ...", fg_color="#0F172A", height=220,
            corner_radius=10, text_color=AppStyle.TEXT_MUTED
        )
        self.lbl_iot.pack(fill="x", padx=14, pady=(4, 8))

        self.lbl_cam_status = ctk.CTkLabel(
            p, text="⬤  Camera xe vào đang chờ khởi động",
            font=AppStyle.SMALL_FONT, text_color=AppStyle.TEXT_MUTED
        )
        self.lbl_cam_status.pack(anchor="w", padx=14, pady=(0, 10))

        self.local_cam = CameraHandler(self.lbl_local, callback=self._on_barcode, on_detection=self._on_detection)
        self.iot_cam = IoTCameraHandler(self.lbl_iot, on_detection=self._on_detection)

    def _scan_from_test_folder(self):
        test_dir = Path("/home/minhviet/Documents/TestCamera")
        if not test_dir.exists():
            self._show_status_alert(f"Lỗi: Thư mục không tồn tại: {test_dir}", "red")
            return
        found_code = None
        if zbar_decode:
            for ext in ["*.jpg", "*.png", "*.jpeg"]:
                for fp in test_dir.glob(ext):
                    frame = cv2.imread(str(fp))
                    if frame is not None:
                        decoded = zbar_decode(frame)
                        if decoded:
                            found_code = decoded[0].data.decode("utf-8").strip()
                            break
                if found_code:
                    break
        if found_code:
            self._set_barcode(found_code)
        else:
            self._show_status_alert("Không tìm thấy mã QR/Barcode trong thư mục.", "orange")

    # ── Right panel (form + Treeview) ─────────────────────────────────────────
    def _build_right_panel(self):
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # ── Form xử lý xe vào ────────────────────────────────────────────────
        p = ctk.CTkFrame(right, fg_color=AppStyle.CARD_BG, corner_radius=14)
        p.grid(row=0, column=0, sticky="ew", padx=(5, 8), pady=(8, 5))

        title_frame = ctk.CTkFrame(p, fg_color="transparent")
        title_frame.pack(fill="x", padx=14, pady=(14, 8))
        
        ctk.CTkLabel(
            title_frame, text="📋  Xử lý xe vào",
            font=AppStyle.SUBTITLE_FONT, text_color=AppStyle.PRIMARY
        ).pack(side="left")

        ctk.CTkButton(
            title_frame, text="🗑 Xóa", width=60, height=28,
            fg_color=AppStyle.SURFACE, hover_color=AppStyle.BORDER,
            text_color=AppStyle.TEXT_SECONDARY, font=AppStyle.SMALL_FONT,
            command=self._clear
        ).pack(side="right")

        # Barcode entry
        self.ent_barcode = ctk.CTkEntry(
            p, placeholder_text="Quét / nhập barcode · QR · REFC",
            height=36, fg_color=AppStyle.SURFACE, border_color=AppStyle.BORDER,
            text_color=AppStyle.TEXT_PRIMARY
        )
        self.ent_barcode.pack(fill="x", padx=14, pady=(0, 6))
        self.ent_barcode.bind("<Return>", lambda e: self._preview())

        # Plate entry
        self.ent_plate = ctk.CTkEntry(
            p, placeholder_text="Biển số (tự động từ camera IoT)",
            height=36, fg_color=AppStyle.SURFACE, border_color=AppStyle.BORDER,
            text_color=AppStyle.TEXT_PRIMARY
        )
        self.ent_plate.pack(fill="x", padx=14, pady=(0, 8))

        # Buttons (đã loại bỏ do chuyển sang tự động hóa)
        ctk.CTkLabel(p, text="Luồng xe vào đã được tự động hóa. Vui lòng quét mã.", font=AppStyle.SMALL_FONT, text_color=AppStyle.SUCCESS).pack(fill="x", padx=14, pady=(0, 10))

        # Info labels (đồng bộ layout giống Xe Ra)
        inf = ctk.CTkFrame(p, fg_color=AppStyle.SURFACE, corner_radius=10)
        inf.pack(fill="x", padx=14, pady=(0, 14))

        def _row(label, attr, bold=False):
            f = ctk.CTkFrame(inf, fg_color="transparent")
            f.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(f, text=label, font=AppStyle.SMALL_FONT,
                         text_color=AppStyle.TEXT_MUTED, width=130, anchor="w"
                         ).pack(side="left")
            fnt = AppStyle.BODY_BOLD if bold else AppStyle.BODY_FONT
            lbl = ctk.CTkLabel(f, text="-", font=fnt,
                               text_color=AppStyle.TEXT_PRIMARY, anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            setattr(self, attr, lbl)

        _row("Chủ xe:",         "inf_name")
        _row("MSSV:",           "inf_id")
        _row("Biển số:",        "inf_plate", True)
        _row("Thời gian vào:",  "inf_time")
        _row("Số dư:",          "inf_balance")
        _row("Khóa xe:",        "inf_lock")

        # ── Treeview xe đang đỗ ──────────────────────────────────────────────
        h = ctk.CTkFrame(right, fg_color=AppStyle.CARD_BG, corner_radius=14)
        h.grid(row=1, column=0, sticky="nsew", padx=(5, 8), pady=(5, 8))
        h.grid_rowconfigure(1, weight=1)
        h.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(h, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(14, 6))
        ctk.CTkLabel(
            hdr, text="🚗  Danh sách xe đang đỗ",
            font=AppStyle.SUBTITLE_FONT, text_color=AppStyle.PRIMARY
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="⟳", width=36, fg_color=AppStyle.PRIMARY,
            command=self._refresh_active_list
        ).pack(side="right")

        tf = ctk.CTkFrame(h, fg_color="transparent")
        tf.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        tf.grid_columnconfigure(0, weight=1)
        tf.grid_rowconfigure(0, weight=1)

        # Style cho Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("XeVao.Treeview", rowheight=26, font=("Helvetica", 11),
                        background="#FFFFFF", fieldbackground="#FFFFFF",
                        foreground="#1F2937")
        style.configure("XeVao.Treeview.Heading", font=("Helvetica", 11, "bold"),
                        background="#EEF2F7", foreground="#3B5998")
        style.map("XeVao.Treeview",
                  background=[("selected", "#3B82F6")],
                  foreground=[("selected", "white")])

        cols = ("BienSo", "ChuXe", "MSSV", "GioVao")
        self.active_tree = ttk.Treeview(
            tf, columns=cols, show="headings",
            style="XeVao.Treeview", height=8
        )
        headings = {"BienSo": "Biển số", "ChuXe": "Chủ xe", "MSSV": "MSSV", "GioVao": "Giờ vào"}
        widths = [100, 140, 80, 130]
        for col, w in zip(cols, widths):
            self.active_tree.heading(col, text=headings[col])
            self.active_tree.column(col, anchor="center", width=w, stretch=False)

        sy = ttk.Scrollbar(tf, orient="vertical", command=self.active_tree.yview)
        sx = ttk.Scrollbar(tf, orient="horizontal", command=self.active_tree.xview)
        self.active_tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

        self.active_tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def _clear(self):
        self.ent_barcode.delete(0, "end")
        self.ent_plate.delete(0, "end")
        for a in ("inf_name", "inf_id", "inf_plate", "inf_time", "inf_balance", "inf_lock"):
            getattr(self, a).configure(text="-", text_color=AppStyle.TEXT_PRIMARY)

    def _on_barcode(self, code: str):
        if code:
            self.main_app.run_in_main_thread(lambda: self._set_barcode(code))

    def _set_barcode(self, code: str):
        self._last_scanned_code = code
        display_code = code
        if "MSSV" in code and code.startswith("{"):
            try:
                import json
                data = json.loads(code)
                display_code = data.get("MSSV", code)
            except Exception: pass

        self.ent_barcode.delete(0, "end")
        self.ent_barcode.insert(0, display_code)
        
        # Bắt đầu giao thức xe vào (INBOUND PROTOCOL)
        self._execute_inbound_protocol(code)

    def _execute_inbound_protocol(self, full_code: str):
        """Lập trình logic xử lý cho Luồng Xe Vào (INBOUND PROTOCOL)."""
        self.lbl_cam_status.configure(text="🟡 Đang xử lý Luồng Xe Vào...", text_color=AppStyle.WARNING)
        
        # Bước 1: Quét mã & Đối chiếu
        student_info = lookup_by_barcode(full_code)
        
        # Lỗi 1 (Sai mã): Nếu không có dữ liệu
        if not student_info:
            self._show_status_alert("⚠️ Cảnh báo: Người dùng chưa đăng ký trong hệ thống. Vui lòng liên hệ Admin.", "orange")
            return

        # Hiển thị thông tin sơ bộ lên UI
        self._update_info_ui(student_info)
        
        # Kiểm tra Tình trạng Khóa ngay tại bước 1.5
        if student_info.get("tinh_trang") == "Khóa":
            self.lbl_cam_status.configure(text="⛔ Thẻ RFID hiện đang bị KHÓA. Vui lòng liên hệ Admin.", text_color=AppStyle.DANGER)
            # Không hiện popup "quá chớn" ở Xe Vào
            return

        ma_rfid = student_info.get("ma_rfid", full_code)
        bien_so_db = ""
        if student_info.get("vehicles"):
            bien_so_db = student_info["vehicles"][0]["bien_so"]

        # Bước 2: Kiểm tra trạng thái đỗ
        from ..utils.db_local import is_vehicle_in_lot
        active_tx = is_vehicle_in_lot(ma_rfid=ma_rfid, bien_so=bien_so_db)
        
        # Lỗi 2 (Xe ma): Nếu xe ĐÃ ở trong bãi
        if active_tx:
            bs = active_tx.get("BienSo", bien_so_db)
            self._show_status_alert(f"⛔ Lỗi Logic: Xe biển số {bs} hiện đang được ghi nhận ở trong bãi. Yêu cầu kiểm tra lại hệ thống!", "red")
            return

        # Bước 3: Giao tiếp Phần cứng (Trong Thread riêng)
        def _hardware_sync():
            from ..utils.hardware import trigger_ir_sensor, request_esp32_capture
            
            # Lỗi 3 (Mất kết nối IR)
            if not trigger_ir_sensor("in"):
                self.main_app.run_in_main_thread(lambda: self._show_status_alert("🔌 Lỗi thiết bị: Cảm biến IR cổng vào không phản hồi.", "orange"))
                
            # requests.get(URL_ESP32_CAPTURE, timeout=5)
            if not request_esp32_capture("in"):
                self.main_app.run_in_main_thread(lambda: self._show_status_alert("📷 Lỗi Camera: Không thể chụp ảnh từ ESP32 cổng vào.", "red"))

            # Bước 4: Lưu trữ & Cập nhật
            frame = self.local_cam.get_latest_frame()
            # Lưu ảnh vào Lich_su_xe_vao/{YYYYMMDD_HHMMSS}_{BienSo}.jpg
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_plate = (self.ent_plate.get() or bien_so_db or "UNKNOWN").replace("-", "").replace(" ", "")
            filename = f"{timestamp}_{safe_plate}.jpg"
            
            save_dir = Path(__file__).resolve().parents[2] / "Lịch sử biển số xe" / "vao"
            save_dir.mkdir(parents=True, exist_ok=True)
            saved_path = str(save_dir / filename)
            
            if frame is not None:
                cv2.imwrite(saved_path, frame)
            
            # INSERT bản ghi mới vào LichSuVaoRa
            res = process_entry(full_code, self.ent_plate.get() or bien_so_db, saved_path)
            self.main_app.run_in_main_thread(lambda: self._on_protocol_finished(res))

        threading.Thread(target=_hardware_sync, daemon=True).start()

    def _on_protocol_finished(self, res):

        if res.get("ok"):
            self.lbl_cam_status.configure(text="🟢 Xe vào thành công.", text_color=AppStyle.STATUS_OK)
            self._refresh_active_list()
            if callable(self.on_updated):
                self.on_updated()
        else:
            self._show_status_alert(res.get("message", "Lỗi không xác định"), "red")

    def _show_status_alert(self, message: str, color_type: str = "orange", timeout: int = 0):
        """Hiển thị CTkToplevel cảnh báo kiểu chuyên nghiệp."""
        if self._active_popup and self._active_popup.winfo_exists():
            return

        if color_type == "green" or color_type == "success":
            color = AppStyle.SUCCESS
            icon = "✅"
        elif color_type == "orange":
            color = AppStyle.WARNING
            icon = "⚠️"
        else:
            color = AppStyle.DANGER
            icon = "⛔"

        self.lbl_cam_status.configure(text=f"⬤ {message}", text_color=color)

        
        self._active_popup = ctk.CTkToplevel(self)
        self._active_popup.title("Thông báo hệ thống")
        self._active_popup.geometry("500x220")
        self._active_popup.attributes("-topmost", True)
        self._active_popup.resizable(False, False)
        
        # Center the popup
        self._active_popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 250
        y = self.winfo_y() + (self.winfo_height() // 2) - 110
        self._active_popup.geometry(f"+{int(x)}+{int(y)}")

        main_frame = ctk.CTkFrame(self._active_popup, fg_color=AppStyle.CARD_BG, corner_radius=15, border_width=2, border_color=color)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Icon giả (Exclamation mark / Success mark)
        icon_lbl = ctk.CTkLabel(main_frame, text=icon, font=("Helvetica", 40))
        icon_lbl.pack(pady=(15, 5))


        lbl = ctk.CTkLabel(main_frame, text=message, font=("Helvetica", 15, "bold"), text_color=AppStyle.TEXT_PRIMARY, wraplength=440)
        lbl.pack(expand=True, padx=20, pady=10)
        
        btn_ok = ctk.CTkButton(main_frame, text="Đóng (3s)", state="disabled", fg_color=AppStyle.TEXT_SECONDARY, command=self._active_popup.destroy)
        btn_ok.pack(pady=(0, 15), ipadx=20)
        
        def _enable_btn(remaining=3):
            if not self._active_popup or not self._active_popup.winfo_exists():
                return
            if remaining > 0:
                btn_ok.configure(text=f"Đóng ({remaining}s)")
                self._active_popup.after(1000, lambda: _enable_btn(remaining - 1))
            else:
                btn_ok.configure(text="Đã hiểu", state="normal", fg_color=AppStyle.PRIMARY)

        _enable_btn(3)
        
        if timeout > 0:
            self._active_popup.after(timeout, self._active_popup.destroy)


    def _on_detection(self, payload: dict):
        dtype = str(payload.get("type", "")).lower()
        val = str(payload.get("value", "")).strip().upper()
        if dtype == "plate":
            if self.ent_plate.get().strip().upper() != val:
                self.main_app.run_in_main_thread(
                    lambda v=val: (self.ent_plate.delete(0, "end"), self.ent_plate.insert(0, v))
                )
        elif dtype in ("refc", "qr", "barcode"):
            if self.ent_barcode.get().strip().upper() != val:
                self.main_app.run_in_main_thread(
                    lambda v=val: self._set_barcode(v)
                )

    def _preview(self, full_code: str = None):
        bc = full_code or self.ent_barcode.get().strip()
        if not bc:
            return
        self._execute_inbound_protocol(bc)

    def _render_info(self, info):
        self.after(0, lambda: self._update_info_ui(info))

    def _update_info_ui(self, info):
        if not info:
            for a in ("inf_name", "inf_id", "inf_plate", "inf_time", "inf_balance", "inf_lock"):
                getattr(self, a).configure(text="-", text_color=AppStyle.TEXT_PRIMARY)
            return
        self.inf_name.configure(text=info.get("ho_ten", "-"))
        self.inf_id.configure(text=info.get("ma_sv", "-"))

        # Hiển thị biển số
        vehicles = info.get("vehicles", [])
        if vehicles:
            plates = ", ".join(v["bien_so"] for v in vehicles)
            self.inf_plate.configure(text=plates, text_color=AppStyle.SUCCESS)
            # Auto-fill biển số vào ô nhập nếu rỗng
            if not self.ent_plate.get().strip() and vehicles:
                self.ent_plate.delete(0, "end")
                self.ent_plate.insert(0, vehicles[0]["bien_so"])
        else:
            self.inf_plate.configure(text="-", text_color=AppStyle.TEXT_PRIMARY)

        self.inf_time.configure(text=datetime.now().strftime("%H:%M:%S  %d/%m/%Y"))
        self.inf_balance.configure(text=f"{int(info.get('so_du', 0)):,}đ")

        is_locked = info.get("tinh_trang") == "Khóa"
        self.inf_lock.configure(
            text="🔒 Khóa" if is_locked else "🔓 Không khóa",
            text_color=AppStyle.DANGER if is_locked else AppStyle.SUCCESS
        )

    def _show_result(self, res):
        if res.get("ok"):
            self.lbl_cam_status.configure(text="🟢 Xe vào thành công.", text_color=AppStyle.STATUS_OK)
            self._refresh_active_list()
            if callable(self.on_updated):
                self.on_updated()
        else:
            self._show_status_alert(res.get("message", "Lỗi"), "red")

    def _submit(self):
        bc = self.ent_barcode.get().strip()
        pl = self.ent_plate.get().strip()
        if not bc:
            return
        frame = self.local_cam.get_latest_frame()
        saved_path = save_capture(frame, "xe_vao") if frame is not None else None
        threading.Thread(
            target=lambda: self._on_entry_result(process_entry(bc, pl, saved_path or "")),
            daemon=True
        ).start()

    def _on_entry_result(self, res):
        self.main_app.run_in_main_thread(lambda: self._show_result(res))

    def _show_result(self, res):
        if res.get("ok"):
            self._show_status_alert(res.get("message"), "green")
            self._refresh_active_list()
            if callable(self.on_updated):
                self.on_updated()
        else:
            self._show_warning_popup("⚠ Lỗi Xe Vào", res.get("message"))

    # ── Treeview refresh ──────────────────────────────────────────────────────
    def _refresh_active_list(self):
        threading.Thread(target=self._load_active_data, daemon=True).start()

    def _load_active_data(self):
        data = get_active(50)
        self.main_app.run_in_main_thread(lambda d=data: self._update_active_tree(d))

    def _update_active_tree(self, data):
        for item in self.active_tree.get_children():
            self.active_tree.delete(item)
        if not data:
            return
        for item in data:
            time_in = item.get("time_in", "-")
            if isinstance(time_in, datetime):
                time_in = time_in.strftime("%H:%M %d/%m/%Y")
            elif isinstance(time_in, str):
                try:
                    time_in = datetime.fromisoformat(time_in).strftime("%H:%M %d/%m/%Y")
                except (ValueError, TypeError):
                    pass
            self.active_tree.insert("", "end", values=(
                item.get("license_plate", "-"),
                item.get("owner_name", "-"),
                item.get("owner_identity", "-"),
                time_in,
            ))

    # ── Camera lifecycle ──────────────────────────────────────────────────────
    def start_cameras(self):
        print("[Camera] Đang khởi động camera...")
        self.cancel_transition()
        self.local_cam.start()
        self.iot_cam.start()
        self._check_camera_status()
        print("[Camera] Camera đã khởi động.")

    def _check_camera_status(self):
        """Kiểm tra trạng thái camera (xanh/vàng/đỏ)."""
        if not self.local_cam.base.running: return
        
        now = time.time()
        last_frame = self.local_cam.base.last_frame_ts
        diff = now - last_frame if last_frame > 0 else 999
        
        if diff < 2.0:
            # Màu xanh: hoạt động bình thường
            self.lbl_cam_status.configure(text="⬤ Camera xe vào đang hoạt động (Online)", text_color=AppStyle.STATUS_OK)
        elif diff < 10.0:
            # Màu vàng: đang quét (đợi tín hiệu)
            self.lbl_cam_status.configure(text=f"⬤ Đang chờ tín hiệu camera ({int(diff)}s)...", text_color=AppStyle.WARNING)
        else:
            # Màu đỏ: lỗi hệ thống (quá 10s)
            self.lbl_cam_status.configure(text="⛔ Lỗi hệ thống: Camera không phản hồi quá 10s!", text_color=AppStyle.DANGER)
            
        self.after(1000, self._check_camera_status)

    def stop_cameras(self):
        self.local_cam.stop()
        self.iot_cam.stop()
        self.lbl_cam_status.configure(
            text="⬤  Camera xe vào đang dừng", text_color=AppStyle.TEXT_MUTED
        )

    def begin_exit_transition(self, s=3, on_complete=None):
        self.cancel_transition()
        self._transition_remaining = s
        self._transition_done = lambda: (self.stop_cameras(), on_complete() if on_complete else None)
        self._tick()

    def _tick(self):
        if self._transition_remaining > 0:
            self.lbl_cam_status.configure(
                text=f"⏳  Chuyển sang Xe Ra sau {self._transition_remaining}s...",
                text_color=AppStyle.WARNING
            )
            self._transition_remaining -= 1
            self._transition_job = self.after(1000, self._tick)
        else:
            cb = self._transition_done
            self._transition_done = None
            self._transition_job = None
            if cb:
                cb()

    def cancel_transition(self):
        if self._transition_job:
            self.after_cancel(self._transition_job)
        self._transition_job = None
        self._transition_done = None

    def get_latest_frame(self):
        return self.local_cam.get_latest_frame()
