# gui/pages/xe_ra_page.py
"""
Tab Xe Ra:
- Dual camera (laptop + IoT)
- Fuzzy plate match + QR/barcode check
- Phí: 6-17:30 → 2000đ, 17:30-23 → 3000đ, sau 23h → từ chối
- Cảnh báo đỏ nếu xe bị khóa, cam nếu thiếu tiền
- Ghi DB khi tất cả hợp lệ
"""
import os
import threading
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

if (__package__ or "").startswith("gui"):
    from ..styles import AppStyle
    from ..utils.camera import CameraHandler, IoTCameraHandler, save_capture
    from ..utils.db_local import process_exit, calc_fee
else:
    from gui.styles import AppStyle
    from gui.utils.camera import CameraHandler, IoTCameraHandler, save_capture
    from gui.utils.db_local import process_exit, calc_fee


class XeRaPage(ctk.CTkFrame):
    def __init__(self, parent, main_app, on_transaction_updated=None):
        super().__init__(parent, fg_color="transparent")
        self.main_app = main_app
        self.on_updated = on_transaction_updated
        self._waiting = False

        self.grid_columnconfigure(0, weight=55)
        self.grid_columnconfigure(1, weight=45)
        self.grid_rowconfigure(0, weight=1)

        self._build_cam_panel()
        self._build_right_panel()

    # ── Camera panel ──────────────────────────────────────────────────────────
    def _build_cam_panel(self):
        p = ctk.CTkFrame(self, fg_color=AppStyle.CARD_BG, corner_radius=14)
        p.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="nsew")

        ctk.CTkLabel(p, text="📷  Camera Giám Sát — Xe Ra",
                     font=AppStyle.SUBTITLE_FONT, text_color=AppStyle.PRIMARY
                     ).pack(anchor="w", padx=14, pady=(14, 4))

        ctk.CTkLabel(p, text="Laptop camera  (barcode · QR · REFC · biển số)",
                     font=AppStyle.SMALL_FONT,
                     text_color=AppStyle.TEXT_SECONDARY).pack(anchor="w", padx=14)
        self.lbl_local = ctk.CTkLabel(
            p, text="Camera đang dừng...", fg_color="#0F172A", height=220,
            corner_radius=10, text_color=AppStyle.TEXT_MUTED)
        self.lbl_local.pack(fill="x", padx=14, pady=(4, 8))

        ctk.CTkLabel(p, text="IoT ESP32 camera  (ảnh từ inbox thư mục)",
                     font=AppStyle.SMALL_FONT,
                     text_color=AppStyle.TEXT_SECONDARY).pack(anchor="w", padx=14)
        self.lbl_iot = ctk.CTkLabel(
            p, text="Camera đang dừng...", fg_color="#0F172A", height=220,
            corner_radius=10, text_color=AppStyle.TEXT_MUTED)
        self.lbl_iot.pack(fill="x", padx=14, pady=(4, 8))

        self.lbl_cam_status = ctk.CTkLabel(
            p, text="⬤  Camera xe ra đang dừng (chờ chuyển tab)",
            font=AppStyle.SMALL_FONT, text_color=AppStyle.TEXT_MUTED)
        self.lbl_cam_status.pack(anchor="w", padx=14, pady=(0, 10))

        # Form trong cam panel
        self.ent_barcode = ctk.CTkEntry(
            p, placeholder_text="Quét / nhập barcode · QR · REFC",
            height=36, fg_color=AppStyle.SURFACE, border_color=AppStyle.BORDER,
            text_color=AppStyle.TEXT_PRIMARY)
        self.ent_barcode.pack(fill="x", padx=14, pady=(0, 6))

        self.ent_plate = ctk.CTkEntry(
            p, placeholder_text="Biển số (tự động từ YOLOv8 Roboflow)",
            height=36, fg_color=AppStyle.SURFACE, border_color=AppStyle.BORDER,
            text_color=AppStyle.TEXT_PRIMARY)
        self.ent_plate.pack(fill="x", padx=14, pady=(0, 8))

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkLabel(row, text="Lane:", font=AppStyle.BODY_FONT,
                     text_color=AppStyle.TEXT_SECONDARY).pack(side="left")
        self.lane = ctk.CTkOptionMenu(row, values=["A", "B", "C"], width=70,
                                      fg_color=AppStyle.SURFACE,
                                      button_color=AppStyle.PRIMARY)
        self.lane.pack(side="left", padx=8)
        self.lane.set("A")
        self.btn_confirm = ctk.CTkButton(
            row, text="✔ Xác nhận xe ra  (giữ yên 2-3s)",
            fg_color=AppStyle.SUCCESS, hover_color=AppStyle.SUCCESS_DARK,
            font=AppStyle.BODY_BOLD, command=self._submit)
        self.btn_confirm.pack(side="left", padx=(8, 4))
        ctk.CTkButton(row, text="Xóa", width=55,
                      fg_color=AppStyle.SURFACE, hover_color=AppStyle.BORDER,
                      text_color=AppStyle.TEXT_SECONDARY,
                      command=self._clear).pack(side="left", padx=4)

        self.local_cam = CameraHandler(
            self.lbl_local, callback=self._on_barcode,
            on_detection=self._on_detection)
        self.iot_cam = IoTCameraHandler(self.lbl_iot, on_detection=self._on_detection)

    # ── Right panel ───────────────────────────────────────────────────────────
    def _build_right_panel(self):
        p = ctk.CTkFrame(self, fg_color=AppStyle.CARD_BG, corner_radius=14)
        p.grid(row=0, column=1, padx=(4, 8), pady=8, sticky="nsew")

        ctk.CTkLabel(p, text="📊  Kết Quả Đối Soát",
                     font=AppStyle.SUBTITLE_FONT, text_color=AppStyle.PRIMARY
                     ).pack(anchor="w", padx=14, pady=(14, 8))

        # Warning banner (hidden by default)
        self.warn_frame = ctk.CTkFrame(p, fg_color=AppStyle.DANGER,
                                       corner_radius=10)
        self.warn_label = ctk.CTkLabel(
            self.warn_frame, text="", font=AppStyle.BODY_BOLD,
            text_color="white", wraplength=380, justify="left")
        self.warn_label.pack(padx=12, pady=8)

        # Info rows
        inf = ctk.CTkFrame(p, fg_color=AppStyle.SURFACE, corner_radius=10)
        inf.pack(fill="x", padx=14, pady=(0, 8))

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

        _row("Họ tên:",        "res_name")
        _row("MSSV:",          "res_id")
        _row("Biển số khớp:", "res_plate", True)
        _row("Điểm khớp:",    "res_score")
        _row("Số dư trước:",  "res_balance")
        _row("Phí gửi xe:",   "res_fee", True)
        _row("Số dư còn:",    "res_remain")
        _row("Thời gian ra:", "res_time")
        _row("Quyết định:",   "res_decision", True)

        # Compare images
        img_f = ctk.CTkFrame(p, fg_color=AppStyle.SURFACE, corner_radius=10)
        img_f.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(img_f, text="Ảnh biển số xe ra:",
                     font=AppStyle.SMALL_FONT,
                     text_color=AppStyle.TEXT_MUTED).pack(anchor="w", padx=10, pady=(8, 2))
        self.img_exit = ctk.CTkLabel(
            img_f, text="Chưa có ảnh ra", height=120,
            fg_color=AppStyle.CARD_BG, corner_radius=8,
            text_color=AppStyle.TEXT_MUTED)
        self.img_exit.pack(fill="x", padx=10, pady=(0, 10))

        # Result textbox
        ctk.CTkLabel(p, text="Chi tiết xử lý:", font=AppStyle.SMALL_FONT,
                     text_color=AppStyle.TEXT_MUTED).pack(anchor="w", padx=14)
        self.result_box = ctk.CTkTextbox(p, height=200, fg_color=AppStyle.SURFACE,
                                         text_color=AppStyle.TEXT_SECONDARY,
                                         font=AppStyle.SMALL_FONT)
        self.result_box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.result_box.insert("1.0", "Chưa có giao dịch xe ra.")
        self.result_box.configure(state="disabled")

    # ── Camera callbacks ──────────────────────────────────────────────────────
    def _on_barcode(self, code: str):
        code = (code or "").strip()
        if code:
            def _update():
                self.ent_barcode.delete(0, "end")
                self.ent_barcode.insert(0, code)
                self.lbl_cam_status.configure(
                    text=f"⬤  Đã quét barcode: {code}",
                    text_color=AppStyle.STATUS_OK)
            self.main_app.run_in_main_thread(_update)

    def _on_detection(self, payload: dict):
        self.main_app.run_in_main_thread(lambda p=payload: self._apply_detection(p))

    def _apply_detection(self, payload: dict):
        dtype = str(payload.get("type", "")).lower()
        value = str(payload.get("value", "")).strip()
        conf = float(payload.get("confidence", 0) or 0)
        src = payload.get("source", "-")
        if not value:
            return
        self.lbl_cam_status.configure(
            text=f"⬤  [{src}] {dtype.upper()}: {value}  ({conf:.0f}%)",
            text_color=AppStyle.STATUS_INFO)
        if dtype == "plate" and conf >= 45.0:
            if self.ent_plate.get().strip().upper() != value.upper():
                self.ent_plate.delete(0, "end")
                self.ent_plate.insert(0, value)
        if dtype in ("refc", "qr") and conf >= 70.0:
            if self.ent_barcode.get().strip() != value:
                self.ent_barcode.delete(0, "end")
                self.ent_barcode.insert(0, value)

    # ── Submit ────────────────────────────────────────────────────────────────
    def _submit(self):
        if self._waiting:
            return
        bc = self.ent_barcode.get().strip()
        if not bc:
            messagebox.showwarning("Thiếu dữ liệu", "Cần barcode / QR để xử lý xe ra.")
            return

        # Kiểm tra giờ
        fee = calc_fee()
        if fee == -1:
            self._show_warn(
                "⛔  NGOÀI GIỜ HOẠT ĐỘNG\n23:00 – 06:00 không nhận xe ra!\n"
                "Vui lòng liên hệ bảo vệ.", color=AppStyle.DANGER)
            return

        self._waiting = True
        self.btn_confirm.configure(state="disabled")
        self.lbl_cam_status.configure(
            text="📸  Đứng yên 2-3 giây để chụp ảnh đối soát...",
            text_color=AppStyle.WARNING)
        self.after(2500, self._submit_after_stable)

    def _submit_after_stable(self):
        bc = self.ent_barcode.get().strip()
        plate = self.ent_plate.get().strip()

        frame = self.local_cam.get_latest_frame()
        saved_path = save_capture(frame, "xe_ra") if frame is not None else None

        def _work():
            result = process_exit(bc, plate, saved_path or "")
            self.main_app.run_in_main_thread(lambda: self._on_exit_result(result, saved_path, plate))

        threading.Thread(target=_work, daemon=True).start()

    def _on_exit_result(self, result: dict, saved_path, plate):
        self._waiting = False
        self.btn_confirm.configure(state="normal")
        self.lbl_cam_status.configure(
            text="⬤  Camera xe ra đang hoạt động", text_color=AppStyle.STATUS_OK)

        ok = result.get("ok", False)
        msg = result.get("message", "")
        st = result.get("student") or {}

        # Cảnh báo xe bị khóa
        if result.get("locked"):
            self._show_warn(
                f"⛔  XE BỊ KHÓA!\nChủ xe: {st.get('ho_ten','?')}\n{msg}",
                color=AppStyle.DANGER)
            if hasattr(self.main_app, "show_lock_warning"):
                self.main_app.show_lock_warning(
                    st.get("ho_ten", "?"), plate, msg)
            self._update_result_labels(result, st)
            return

        # Cảnh báo thiếu tiền
        if result.get("insufficient"):
            self._show_warn(f"⚠  KHÔNG ĐỦ TIỀN\n{msg}", color=AppStyle.WARNING)
            self._update_result_labels(result, st)
            return

        # Xử lý bình thường
        self._hide_warn()
        self._update_result_labels(result, st)

        # Hiển thị ảnh ra
        if saved_path:
            try:
                img = Image.open(saved_path).convert("RGB")
                nw = 420; nh = int(img.height * nw / img.width)
                nh = min(nh, 140)
                img = img.resize((nw, nh))
                ci = ctk.CTkImage(light_image=img, dark_image=img, size=(nw, nh))
                self.img_exit.configure(image=ci, text="", height=nh)
                self.img_exit.image = ci
            except Exception:
                pass

        if ok:
            messagebox.showinfo("✔ Xe Ra", msg)
            if callable(self.on_updated):
                self.on_updated()
        else:
            messagebox.showwarning("⚠ Không hợp lệ", msg)

    def _update_result_labels(self, result: dict, st: dict):
        fee = result.get("fee", 0) or 0
        so_du = int(st.get("so_du", 0) or 0)
        ok = result.get("ok", False)

        self.res_name.configure(text=st.get("ho_ten", "-") or "-")
        self.res_id.configure(text=st.get("ma_sv", "-") or "-")
        self.res_plate.configure(
            text=result.get("matched_plate", "-") or "-",
            text_color=AppStyle.SUCCESS if ok else AppStyle.WARNING)
        score = result.get("plate_score", 0)
        self.res_score.configure(
            text=f"{score}%" if score else "-",
            text_color=AppStyle.SUCCESS if score >= 75 else AppStyle.WARNING)
        self.res_balance.configure(text=f"{so_du:,}đ")
        self.res_fee.configure(
            text=f"{fee:,}đ" if fee else "-",
            text_color=AppStyle.WARNING)
        remain = so_du - fee if ok else so_du
        self.res_remain.configure(
            text=f"{remain:,}đ",
            text_color=AppStyle.SUCCESS if remain >= 0 else AppStyle.DANGER)
        self.res_time.configure(
            text=datetime.now().strftime("%H:%M:%S  %d/%m/%Y"),
            text_color=AppStyle.STATUS_INFO)
        dec_text = "✔ CHẤP NHẬN" if ok else "✖ TỪ CHỐI"
        self.res_decision.configure(
            text=dec_text,
            text_color=AppStyle.SUCCESS if ok else AppStyle.DANGER)

        # Textbox log
        lines = [
            f"Trạng thái: {'OK' if ok else 'FAIL'}",
            f"Thông điệp: {result.get('message','-')}",
            f"Biển số quét: {self.ent_plate.get().strip() or '-'}",
            f"Biển số khớp: {result.get('matched_plate','-')}",
            f"Điểm khớp: {score}%",
            f"Phí: {fee:,}đ",
            f"Số dư trước: {so_du:,}đ",
            f"Số dư sau: {remain:,}đ",
            f"Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
        ]
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", "\n".join(lines))
        self.result_box.configure(state="disabled")

    def _show_warn(self, text: str, color: str = None):
        self.warn_label.configure(text=text)
        self.warn_frame.configure(fg_color=color or AppStyle.DANGER)
        self.warn_frame.pack(fill="x", padx=14, pady=(0, 8),
                             before=self.res_name.master.master)

    def _hide_warn(self):
        self.warn_frame.pack_forget()

    # ── Clear ─────────────────────────────────────────────────────────────────
    def _clear(self):
        self.ent_barcode.delete(0, "end")
        self.ent_plate.delete(0, "end")
        self._hide_warn()
        for a in ("res_name","res_id","res_plate","res_score","res_balance",
                  "res_fee","res_remain","res_time","res_decision"):
            getattr(self, a).configure(text="-", text_color=AppStyle.TEXT_PRIMARY)
        self.img_exit.configure(image=None, text="Chưa có ảnh ra")
        self.img_exit.image = None
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", "Chưa có giao dịch xe ra.")
        self.result_box.configure(state="disabled")

    # ── Camera lifecycle ──────────────────────────────────────────────────────
    def start_cameras(self):
        cam_id = int(os.getenv("LAPTOP_CAMERA_ID", "0"))
        self.local_cam.start(camera_id=cam_id)
        self.iot_cam.start()
        self.lbl_cam_status.configure(
            text="⬤  Camera xe ra đang hoạt động", text_color=AppStyle.STATUS_OK)

    def stop_cameras(self):
        self.local_cam.stop()
        self.iot_cam.stop()
        self.lbl_cam_status.configure(
            text="⬤  Camera xe ra đang dừng", text_color=AppStyle.TEXT_MUTED)
