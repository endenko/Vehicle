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
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox

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
            messagebox.showerror("Lỗi", f"Thư mục không tồn tại: {test_dir}")
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
            messagebox.showwarning("Không tìm thấy", "Không có mã QR/Barcode trong thư mục.")

    # ── Right panel (form + Treeview) ─────────────────────────────────────────
    def _build_right_panel(self):
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # ── Form xử lý xe vào ────────────────────────────────────────────────
        p = ctk.CTkFrame(right, fg_color=AppStyle.CARD_BG, corner_radius=14)
        p.grid(row=0, column=0, sticky="ew", padx=(5, 8), pady=(8, 5))

        ctk.CTkLabel(
            p, text="📋  Xử lý xe vào",
            font=AppStyle.SUBTITLE_FONT, text_color=AppStyle.PRIMARY
        ).pack(anchor="w", padx=14, pady=(14, 8))

        # Barcode entry
        self.ent_barcode = ctk.CTkEntry(
            p, placeholder_text="Quét / nhập barcode · QR · REFC",
            height=36, fg_color=AppStyle.SURFACE, border_color=AppStyle.BORDER,
            text_color=AppStyle.TEXT_PRIMARY
        )
        self.ent_barcode.pack(fill="x", padx=14, pady=(0, 6))

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
    def _on_barcode(self, code: str):
        if code:
            self.main_app.run_in_main_thread(lambda: self._set_barcode(code))

    def _set_barcode(self, code: str):
        self.ent_barcode.delete(0, "end")
        self.ent_barcode.insert(0, code)
        self._preview()

    def _on_detection(self, payload: dict):
        dtype = str(payload.get("type", "")).lower()
        if dtype == "plate":
            val = str(payload.get("value", "")).strip().upper()
            if self.ent_plate.get().strip().upper() != val:
                self.main_app.run_in_main_thread(
                    lambda v=val: (self.ent_plate.delete(0, "end"), self.ent_plate.insert(0, v))
                )

    def _preview(self):
        bc = self.ent_barcode.get().strip()
        if not bc:
            return
        threading.Thread(target=lambda: self._render_info(lookup_by_barcode(bc)), daemon=True).start()

    def _render_info(self, info):
        self.after(0, lambda: self._update_info_ui(info))

    def _update_info_ui(self, info):
        if not info:
            for a in ("inf_name", "inf_id", "inf_plate", "inf_time", "inf_balance", "inf_lock"):
                getattr(self, a).configure(text="-", text_color=AppStyle.TEXT_PRIMARY)
            # Hiện popup cảnh báo chưa đăng ký
            self._show_warning_popup("⚠ Cảnh báo vi phạm", "NGƯỜI DÙNG CHƯA ĐĂNG KÝ!")
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
        
        # Tự động submit sau khi preview
        if not is_locked:
            self.after(500, self._submit)

    def _show_warning_popup(self, title: str, message: str):
        """CTkToplevel cảnh báo (nhấp nháy đỏ)."""
        popup = ctk.CTkToplevel(self)
        popup.title(title)
        popup.geometry("400x180")
        popup.resizable(False, False)
        
        self.after(100, popup.grab_set)
        
        lbl = ctk.CTkLabel(
            popup, 
            text=f"⚠ {message}", 
            font=("Helvetica", 18, "bold"),
            text_color=AppStyle.DANGER,
            wraplength=350
        )
        lbl.pack(expand=True, pady=20)
        
        ctk.CTkButton(
            popup, text="Đóng", fg_color=AppStyle.SURFACE,
            text_color=AppStyle.TEXT_PRIMARY,
            command=popup.destroy, width=120
        ).pack(pady=10)
        
        # Nhấp nháy viền đỏ
        colors = [AppStyle.DANGER, AppStyle.TEXT_SECONDARY]
        def _blink(idx=0):
            if not popup.winfo_exists():
                return
            lbl.configure(text_color=colors[idx % 2])
            popup.after(500, _blink, idx + 1)
        _blink()

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
            messagebox.showinfo("✔ Xe Vào", res.get("message"))
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
        self.lbl_cam_status.configure(
            text="⬤  Camera xe vào đang hoạt động", text_color=AppStyle.STATUS_OK
        )
        print("[Camera] Camera đã khởi động.")

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
