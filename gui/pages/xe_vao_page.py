# gui/pages/xe_vao_page.py
import os
import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
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

    def _build_cam_panel(self):
        p = ctk.CTkFrame(self, fg_color=AppStyle.CARD_BG, corner_radius=14)
        p.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="nsew")

        ctk.CTkLabel(p, text="Camera laptop + camera IoT — Xe Vào", font=AppStyle.SUBTITLE_FONT, text_color=AppStyle.PRIMARY_DARK).pack(anchor="w", padx=20, pady=(20, 10))

        self.lbl_local = ctk.CTkLabel(p, text="Camera laptop (Quét Barcode/QR)", fg_color=AppStyle.SURFACE, height=220, corner_radius=10, text_color=AppStyle.TEXT_MUTED)
        self.lbl_local.pack(fill="x", padx=20, pady=(5, 10))

        tf = ctk.CTkFrame(p, fg_color="transparent")
        tf.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkButton(tf, text="Quét từ thư mục (TestCamera)", command=self._scan_from_test_folder, fg_color=AppStyle.SUCCESS, height=32).pack(side="left")

        self.lbl_iot = ctk.CTkLabel(p, text="Camera IoT (Nhận diện biển số)", fg_color=AppStyle.SURFACE, height=220, corner_radius=10, text_color=AppStyle.TEXT_MUTED)
        self.lbl_iot.pack(fill="x", padx=20, pady=(5, 10))

        self.lbl_cam_status = ctk.CTkLabel(p, text="Camera xe vào đang hoạt động.", font=AppStyle.BODY_FONT, text_color=AppStyle.TEXT_SECONDARY)
        self.lbl_cam_status.pack(anchor="w", padx=20, pady=(0, 10))

        self.local_cam = CameraHandler(self.lbl_local, callback=self._on_barcode, on_detection=self._on_detection)
        self.iot_cam = IoTCameraHandler(self.lbl_iot, on_detection=self._on_detection)
        # Bỏ khởi động tại đây để tránh treo Linux
        # self.start_cameras() 

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
                if found_code: break
        if found_code: self._set_barcode(found_code)
        else: messagebox.showwarning("Không tìm thấy", "Không có mã QR/Barcode trong thư mục.")

    def _build_right_panel(self):
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        p = ctk.CTkFrame(right, fg_color=AppStyle.CARD_BG, corner_radius=14)
        p.grid(row=0, column=0, sticky="ew", pady=(0, 15))

        ctk.CTkLabel(p, text="Xử lý xe vào", font=AppStyle.SUBTITLE_FONT, text_color=AppStyle.PRIMARY_DARK).pack(anchor="w", padx=20, pady=(20, 15))

        self.ent_barcode = ctk.CTkEntry(p, placeholder_text="Nhap/quet barcode", height=40, fg_color=AppStyle.SURFACE)
        self.ent_barcode.pack(fill="x", padx=20, pady=(0, 10))
        self.ent_plate = ctk.CTkEntry(p, placeholder_text="Bien so", height=40, fg_color=AppStyle.SURFACE)
        self.ent_plate.pack(fill="x", padx=20, pady=(0, 15))

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 15))
        ctk.CTkLabel(row, text="Lane", font=AppStyle.BODY_FONT).pack(side="left")
        self.lane = ctk.CTkOptionMenu(row, values=["A", "B", "C"], width=80, fg_color=AppStyle.PRIMARY)
        self.lane.pack(side="left", padx=10); self.lane.set("A")
        
        ctk.CTkButton(row, text="Tra cuu DB", fg_color=AppStyle.PRIMARY, font=AppStyle.BODY_BOLD, command=self._preview).pack(side="left", padx=5)
        ctk.CTkButton(row, text="Xac nhan xe vao", fg_color=AppStyle.SUCCESS, font=AppStyle.BODY_BOLD, command=self._submit).pack(side="left", expand=True, fill="x")

        inf = ctk.CTkFrame(p, fg_color=AppStyle.SURFACE, corner_radius=10)
        inf.pack(fill="x", padx=20, pady=(0, 20))

        def _row(label, attr):
            f = ctk.CTkFrame(inf, fg_color="transparent")
            f.pack(fill="x", padx=15, pady=4)
            ctk.CTkLabel(f, text=label, font=AppStyle.BODY_FONT, width=120, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(f, text="-", font=AppStyle.BODY_FONT, anchor="w")
            lbl.pack(side="left", fill="x", expand=True)
            setattr(self, attr, lbl)

        _row("Chu xe:", "inf_name")
        _row("Ma sv:", "inf_id")
        _row("Thoi gian vao:", "inf_time")
        _row("So du:", "inf_balance")
        _row("Khoa xe:", "inf_lock")

        h = ctk.CTkFrame(right, fg_color=AppStyle.CARD_BG, corner_radius=14)
        h.grid(row=1, column=0, sticky="nsew")
        h.grid_rowconfigure(1, weight=1); h.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(h, text="Danh sách xe đang đỗ", font=AppStyle.SUBTITLE_FONT, text_color=AppStyle.PRIMARY_DARK).pack(anchor="w", padx=20, pady=(20, 10))
        self.hist_box = ctk.CTkTextbox(h, fg_color=AppStyle.SURFACE)
        self.hist_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.hist_box.configure(state="disabled")

    def _on_barcode(self, code: str):
        if code: self.main_app.run_in_main_thread(lambda: self._set_barcode(code))

    def _set_barcode(self, code: str):
        self.ent_barcode.delete(0, "end"); self.ent_barcode.insert(0, code)
        self._preview()

    def _on_detection(self, payload: dict):
        dtype = str(payload.get("type", "")).lower()
        if dtype == "plate":
            val = str(payload.get("value", "")).strip().upper()
            if self.ent_plate.get().strip().upper() != val:
                self.main_app.run_in_main_thread(lambda v=val: (self.ent_plate.delete(0, "end"), self.ent_plate.insert(0, v)))

    def _preview(self):
        bc = self.ent_barcode.get().strip()
        if not bc: return
        threading.Thread(target=lambda: self._render_info(lookup_by_barcode(bc)), daemon=True).start()

    def _render_info(self, info):
        self.after(0, lambda: self._update_info_ui(info))

    def _update_info_ui(self, info):
        if not info:
            for a in ("inf_name","inf_id","inf_time","inf_balance","inf_lock"):
                getattr(self, a).configure(text="-")
            return
        self.inf_name.configure(text=info.get("ho_ten", "-"))
        self.inf_id.configure(text=info.get("ma_sv", "-"))
        self.inf_time.configure(text=datetime.now().strftime("%H:%M:%S %d/%m/%Y"))
        self.inf_balance.configure(text=f"{int(info.get('so_du',0)):,}đ")
        self.inf_lock.configure(text="Khoa" if info.get("tinh_trang") == "Khóa" else "Khong")

    def _submit(self):
        bc = self.ent_barcode.get().strip()
        pl = self.ent_plate.get().strip()
        if not bc: return
        frame = self.local_cam.get_latest_frame()
        saved_path = save_capture(frame, "xe_vao")
        threading.Thread(target=lambda: self._on_entry_result(process_entry(bc, pl, saved_path or "")), daemon=True).start()

    def _on_entry_result(self, res):
        self.main_app.run_in_main_thread(lambda: self._show_result(res))

    def _show_result(self, res):
        if res.get("ok"):
            messagebox.showinfo("Thành công", res.get("message"))
            self._refresh_active_list()
            if callable(self.on_updated): self.on_updated()
        else:
            messagebox.showwarning("Lỗi", res.get("message"))

    def _refresh_active_list(self):
        threading.Thread(target=self._load_active_data, daemon=True).start()

    def _load_active_data(self):
        data = get_active(50)
        text = "\n".join([f"{item['license_plate']} | {item['owner_name']} | {item['time_in']}" for item in data]) if data else "Chưa có xe đang đỗ."
        self.main_app.run_in_main_thread(lambda t=text: self._update_active_ui(t))

    def _update_active_ui(self, text):
        self.hist_box.configure(state="normal")
        self.hist_box.delete("0.0", "end"); self.hist_box.insert("0.0", text)
        self.hist_box.configure(state="disabled")

    def start_cameras(self):
        print("[Camera] Đang khởi động camera...")
        self.cancel_transition()
        self.local_cam.start()
        self.iot_cam.start()
        print("[Camera] Camera đã khởi động.")

    def stop_cameras(self):
        self.local_cam.stop(); self.iot_cam.stop()

    def begin_exit_transition(self, s=3, on_complete=None):
        self.cancel_transition(); self._transition_remaining = s
        self._transition_done = lambda: (self.stop_cameras(), on_complete() if on_complete else None)
        self._tick()

    def _tick(self):
        if self._transition_remaining > 0:
            self.lbl_cam_status.configure(text=f"Chuyen sang Xe Ra sau {self._transition_remaining}s...")
            self._transition_remaining -= 1
            self._transition_job = self.after(1000, self._tick)
        else:
            cb = self._transition_done; self._transition_done = None; self._transition_job = None
            if cb: cb()

    def cancel_transition(self):
        if self._transition_job: self.after_cancel(self._transition_job)
        self._transition_job = None; self._transition_done = None
