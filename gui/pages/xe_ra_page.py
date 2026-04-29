# gui/pages/xe_ra_page.py
"""
Tab Xe Ra — Redesigned:
- Dual camera (laptop + IoT)
- Xóa Lane ComboBox + nút "Xác nhận xe ra"
- Tự động hóa: quét mã → fuzzy match → check khóa/tiền → quyết định
- Thêm CTkLabel 320×240 hiển thị ảnh biển số lúc VÀO để đối chiếu
- Cảnh báo đỏ nhấp nháy nếu xe bị khóa
- Re-scan tự động nếu fuzzy < 75% (dùng .after(), KHÔNG time.sleep)
- Phí gửi xe kèm phụ phí 5,000đ nếu quá 24h
"""
import os
import threading
import time
from datetime import datetime
from tkinter import simpledialog

import customtkinter as ctk
from PIL import Image

try:
    from thefuzz import fuzz
    _HAS_FUZZ = True
except ImportError:
    try:
        from fuzzywuzzy import fuzz
        _HAS_FUZZ = True
    except ImportError:
        _HAS_FUZZ = False



if (__package__ or "").startswith("gui"):
    from ..styles import AppStyle
    from ..utils.camera import CameraHandler, IoTCameraHandler, save_capture
    from ..utils.db_local import (
        append_security_audit,
        calc_fee,
        find_entry_image,
        is_operating_hours,
        process_exit,
    )
else:
    from gui.styles import AppStyle
    from gui.utils.camera import CameraHandler, IoTCameraHandler, save_capture
    from gui.utils.db_local import (
        append_security_audit,
        calc_fee,
        find_entry_image,
        is_operating_hours,
        process_exit,
    )


ADMIN_OVERRIDE_PASSWORD = os.getenv("MANUAL_OVERRIDE_PASSWORD", "SPM-OVERRIDE-2026")


class XeRaPage(ctk.CTkFrame):
    def __init__(self, parent, main_app, on_transaction_updated=None):
        super().__init__(parent, fg_color="transparent")
        self.main_app = main_app
        self.on_updated = on_transaction_updated
        self._waiting = False
        self._blink_job = None
        self._rescan_job = None
        self._active_popup = None
        self._last_processed_code = ""
        self._last_processed_ts = 0.0
        self._scan_cooldown_seconds = 3.0

        self.grid_columnconfigure(0, weight=55)
        self.grid_columnconfigure(1, weight=45)
        self.grid_rowconfigure(0, weight=1)

        self._build_cam_panel()
        self._build_right_panel()

    # ── Camera panel (trái) ───────────────────────────────────────────────────
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
        self.lbl_cam_status.pack(anchor="w", padx=14, pady=(0, 8))

        # Chỉ giữ 2 ô hiển thị (không có Lane, không có nút confirm)
        self.ent_barcode = ctk.CTkEntry(
            p, placeholder_text="Quét / nhập barcode · QR · REFC",
            height=36, fg_color=AppStyle.SURFACE, border_color=AppStyle.BORDER,
            text_color=AppStyle.TEXT_PRIMARY)
        self.ent_barcode.pack(fill="x", padx=14, pady=(0, 6))
        self.ent_barcode.bind("<Return>", lambda e: self._on_barcode(self.ent_barcode.get()))

        self.ent_plate = ctk.CTkEntry(
            p, placeholder_text="Biển số (tự động từ YOLOv8 Roboflow)",
            height=36, fg_color=AppStyle.SURFACE, border_color=AppStyle.BORDER,
            text_color=AppStyle.TEXT_PRIMARY)
        self.ent_plate.pack(fill="x", padx=14, pady=(0, 8))

        # Nút xóa nhỏ
        btn_row = ctk.CTkFrame(p, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkButton(
            btn_row,
            text="Mở Barie Thủ Công",
            width=150,
            fg_color="#FEE2E2",
            hover_color="#FECACA",
            text_color="#B91C1C",
            font=AppStyle.SMALL_FONT,
            command=self._manual_override_dialog,
        ).pack(side="left")
        ctk.CTkButton(btn_row, text="🗑 Xóa", width=80,
                      fg_color=AppStyle.SURFACE, hover_color=AppStyle.BORDER,
                      text_color=AppStyle.TEXT_SECONDARY, font=AppStyle.SMALL_FONT,
                      command=self._clear).pack(side="right")

        # ── (Đã chuyển khung ảnh đối chiếu sang cột phải) ─────────────────────────

        self.local_cam = CameraHandler(
            self.lbl_local, callback=self._on_barcode,
            on_detection=self._on_detection)
        from pathlib import Path
        base_dir = Path(__file__).resolve().parents[2]
        self.iot_cam = IoTCameraHandler(self.lbl_iot, on_detection=self._on_detection, storage_dir=str(base_dir / "Lich_su_xe_ra"))

    # ── Right panel (kết quả đối soát) ────────────────────────────────────────
    def _build_right_panel(self):
        p = ctk.CTkFrame(self, fg_color=AppStyle.CARD_BG, corner_radius=14)
        p.grid(row=0, column=1, padx=(4, 8), pady=8, sticky="nsew")

        # Header: Title + Refresh Button
        header_f = ctk.CTkFrame(p, fg_color="transparent")
        header_f.pack(fill="x", padx=14, pady=(14, 8))
        
        ctk.CTkLabel(header_f, text="📊  Kết Quả Đối Soát",
                     font=AppStyle.SUBTITLE_FONT, text_color=AppStyle.PRIMARY
                     ).pack(side="left")
                     
        ctk.CTkButton(header_f, text="🔄 Làm mới", font=AppStyle.BUTTON_FONT,
                      width=100, height=30, fg_color=AppStyle.SURFACE,
                      text_color=AppStyle.TEXT_PRIMARY, hover_color=AppStyle.CARD_BG,
                      command=self._clear).pack(side="right")

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
        _row("Biển số khớp:",  "res_plate", True)
        _row("Điểm khớp:",    "res_score")
        _row("Thời gian vào:", "res_time_in")
        _row("Số dư trước:",  "res_balance")
        _row("Phí gửi xe:",   "res_fee", True)
        _row("Phụ phí 24h:",  "res_surcharge")
        _row("Số dư còn:",    "res_remain")
        _row("Thời gian ra:", "res_time")
        _row("Quyết định:",   "res_decision", True)

        # Compare images (ảnh vào để đối chiếu)
        img_f = ctk.CTkFrame(p, fg_color=AppStyle.SURFACE, corner_radius=10)
        img_f.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(img_f, text="📸 Ảnh biển số xe lúc VÀO (đối chiếu):",
                     font=AppStyle.SMALL_FONT,
                     text_color=AppStyle.TEXT_MUTED).pack(anchor="w", padx=10, pady=(8, 2))
        self.img_entry_label = ctk.CTkLabel(
            img_f, text="Chưa có ảnh vào", height=120,
            fg_color=AppStyle.CARD_BG, corner_radius=8,
            text_color=AppStyle.TEXT_MUTED)
        self.img_entry_label.pack(fill="x", padx=10, pady=(0, 10))

        # Result textbox
        ctk.CTkLabel(p, text="Chi tiết xử lý:", font=AppStyle.SMALL_FONT,
                     text_color=AppStyle.TEXT_MUTED).pack(anchor="w", padx=14)
        self.result_box = ctk.CTkTextbox(p, height=150, fg_color=AppStyle.SURFACE,
                                         text_color=AppStyle.TEXT_SECONDARY,
                                         font=AppStyle.SMALL_FONT)
        self.result_box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.result_box.insert("1.0", "Chưa có giao dịch xe ra.")
        self.result_box.configure(state="disabled")

    # ── Camera callbacks ──────────────────────────────────────────────────────
    def _on_barcode(self, code: str):
        code = (code or "").strip()
        if code:
            code_key = code.upper()
            now = time.time()
            if code_key == self._last_processed_code and (now - self._last_processed_ts) < self._scan_cooldown_seconds:
                return
            self._last_processed_code = code_key
            self._last_processed_ts = now

            def _update():
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
                self.lbl_cam_status.configure(
                    text=f"⬤  Đã quét barcode: {display_code}",
                    text_color=AppStyle.STATUS_OK)
                # Tự động xử lý xe ra khi quét được mã (OUTBOUND PROTOCOL)
                self._execute_outbound_protocol(code)
            self.main_app.run_in_main_thread(_update)

    def _execute_outbound_protocol(self, full_code: str):
        """Lập trình logic xử lý cho Luồng Xe Ra (OUTBOUND PROTOCOL).
        
        Giao thức mới (ESP32 Integration):
        1. GUI quét mã → Gọi POST /register-student?lane=OUT (httpx, non-blocking)
        2. ESP32 tự chụp ảnh → POST /process-plate?lane=OUT
        3. GUI polling GET /lane-status?lane=OUT để cập nhật kết quả
        """
        if self._waiting: return
        self._waiting = True
        self._retry_count = 0
        self._current_code = full_code

        try:
            self.lbl_cam_status.configure(text="🟡 Đang thực hiện Giao thức Xe Ra...", text_color=AppStyle.WARNING)

            from ..utils.db_local import calc_fee_with_surcharge, is_vehicle_in_lot, lookup_by_barcode
    
            student_info = lookup_by_barcode(full_code)
            if not student_info:
                self._show_status_alert("⚠️ Người dùng chưa đăng ký hệ thống.", "orange", timeout=3000)
                self._waiting = False
                return
    
            ma_sv = student_info.get("ma_sv", full_code)
            ma_rfid = student_info.get("ma_rfid", full_code)
            active_tx = is_vehicle_in_lot(ma_rfid=ma_rfid)
            if not active_tx and student_info.get("vehicles"):
                for vehicle in student_info.get("vehicles", []):
                    active_tx = is_vehicle_in_lot(bien_so=vehicle.get("bien_so"))
                    if active_tx:
                        break
    
            preview_plate = self.ent_plate.get().strip()
            if not preview_plate and student_info.get("vehicles"):
                preview_plate = student_info["vehicles"][0].get("bien_so", "")
    
            self._show_outbound_preview(student_info, active_tx, preview_plate)
            self.update_idletasks()
    
            if not active_tx:
                self._show_status_alert("⛔ Lỗi: Xe này chưa được ghi nhận vào bãi.", "red", timeout=3000)
                self._waiting = False
                return
    
            if not is_operating_hours():
                self._show_status_alert("⛔ Ngoài giờ hoạt động (06:00 – 23:00). Không nhận xe ra!", "red", timeout=3000)
                self._waiting = False
                return
    
            is_locked = student_info.get("tinh_trang") == "Khóa"
            if is_locked:
                self._start_blink_warning()
                self._show_status_alert("🚨 CẢNH BÁO AN NINH: XE ĐANG BỊ KHÓA TRÊN HỆ THỐNG! CHẶN BARIE!", "red", timeout=3000)
                self._update_result_labels({"ok": False, "locked": True, "message": "XE BỊ KHÓA"}, student_info)
                self._waiting = False
                return
    
            fee_info = calc_fee_with_surcharge(active_tx.get("ThoiGianVao"))
            if fee_info.get("rejected"):
                self._show_status_alert("⛔ Từ chối: Ngoài giờ hoạt động.", "red", timeout=3000)
                self._waiting = False
                return
    
            total_fee = fee_info["total"]
            so_du = int(student_info.get("so_du", 0) or 0)
            if so_du < total_fee:
                self._show_status_alert(
                    f"💸 Số dư không đủ! (Cần: {total_fee:,}đ - Còn: {so_du:,}đ). Vui lòng nạp thêm tiền.",
                    "orange",
                    timeout=3000,
                )
                self._update_result_labels({"ok": False, "insufficient": True, "fee_info": fee_info}, student_info)
                self._waiting = False
                return
    
            self.lbl_cam_status.configure(text="📡 Đang đăng ký session với server...", text_color=AppStyle.WARNING)
    
            # Gọi API /register-student trong thread riêng
            def _register_and_wait():
                import httpx
                from smart_parking.config import API_ENDPOINT
    
                try:
                    with httpx.Client(timeout=5.0) as client:
                        resp = client.post(
                            f"{API_ENDPOINT}/register-student",
                            json={"ma_sv": ma_sv, "lane": "OUT"}
                        )
    
                        if resp.status_code == 404:
                            self.main_app.run_in_main_thread(
                                lambda: self._show_auto_close_popup("⚠️ Người dùng chưa đăng ký", "orange", 3000)
                            )
                            self.main_app.run_in_main_thread(lambda: setattr(self, "_waiting", False))
                            return
    
                        if resp.status_code != 200:
                            msg = resp.json().get("detail", "Lỗi server")
                            self.main_app.run_in_main_thread(
                                lambda m=msg: self._show_status_alert(f"⛔ Server: {m}", "red", timeout=3000)
                            )
                            self.main_app.run_in_main_thread(lambda: setattr(self, "_waiting", False))
                            return
    
                        # Thành công → Kiểm tra IR sensor trước khi chờ ESP32
                        self.main_app.run_in_main_thread(
                            lambda: self.lbl_cam_status.configure(
                                text="🔍 Đang kiểm tra cảm biến IR cổng ra...",
                                text_color=AppStyle.WARNING
                            )
                        )
    
                        # Kiểm tra IR sensor: có xe chắn không?
                        ir_ok = True
                        try:
                            ir_resp = client.get(f"{API_ENDPOINT}/check-ir", params={"lane": "OUT"}, timeout=5.0)
                            ir_data = ir_resp.json()
                            if not ir_data.get("detected", False):
                                ir_ok = False
                        except Exception:
                            pass
    
                        if not ir_ok:
                            self.main_app.run_in_main_thread(
                                lambda: (setattr(self, "_waiting", False), self._show_auto_close_popup("🚫 Không có xe tại cổng ra! IR Sensor không phát hiện xe.", "red", 3000))
                            )
                            return
    
                        # IR OK → Chủ động kích hoạt ESP32 chụp ảnh qua server
                        self.main_app.run_in_main_thread(
                            lambda: self.lbl_cam_status.configure(
                                text="📷 Đang yêu cầu ESP32 chụp ảnh cổng ra...",
                                text_color=AppStyle.WARNING
                            )
                        )
                        try:
                            trigger_resp = client.get(f"{API_ENDPOINT}/api/vehicle-detected", params={"lane": "OUT"}, timeout=10.0)
                            print(f"[GUI] Trigger vehicle-detected OUT: {trigger_resp.status_code} → {trigger_resp.text[:200]}")
                        except Exception as trigger_err:
                            print(f"[GUI] Trigger vehicle-detected OUT failed: {trigger_err}")
    
                    # Polling kết quả
                    self.main_app.run_in_main_thread(lambda: self._poll_lane_status_out("OUT", student_info))
    
                except httpx.ConnectError:
                    # Server chưa chạy → Fallback sang logic local
                    self.main_app.run_in_main_thread(
                        lambda: self._fallback_local_outbound(student_info, active_tx, preview_plate)
                    )
                except Exception as e:
                    self.main_app.run_in_main_thread(
                        lambda err=e: self._show_status_alert(f"⛔ Lỗi kết nối server: {err}", "red", timeout=3000)
                    )
                    self.main_app.run_in_main_thread(lambda: setattr(self, "_waiting", False))
    
            threading.Thread(target=_register_and_wait, daemon=True).start()

        except Exception as e:
            self._waiting = False
            self._show_status_alert(f"⛔ Lỗi xử lý xe ra: {e}", "red")
            return

    def _poll_lane_status_out(self, lane: str, student_info: dict, retries: int = 15):
        """Polling GET /lane-status?lane=OUT để cập nhật kết quả từ ESP32 (max 15 giây)."""
        if retries <= 0:
            self._waiting = False
            self.lbl_cam_status.configure(
                text="⏰ Timeout: ESP32 không phản hồi. Vui lòng kiểm tra kết nối hoặc quét lại!",
                text_color=AppStyle.DANGER
            )
            # Show error popup
            self._show_auto_close_popup(
                "⚠️ ESP32 chưa chụp ảnh trong 15 giây. Kiểm tra:\n"
                "• Kết nối WiFi của ESP32?\n"
                "• Cổng camera cửa RA khác lỗi hay không?",
                "orange",
                3000
            )
            return

        def _check():
            import httpx
            from smart_parking.config import API_ENDPOINT
            try:
                with httpx.Client(timeout=3.0) as client:
                    resp = client.get(f"{API_ENDPOINT}/lane-status", params={"lane": lane}, timeout=3.0)
                    return resp.json()
            except Exception as e:
                return {"status": "pending", "error": str(e)}

        def _do_poll():
            try:
                data = _check()
                status = data.get("status", "pending")

                if status == "processing":
                    msg = data.get("message", "Đang xử lý ảnh...")
                    self.lbl_cam_status.configure(text=f"📷 {msg}", text_color=AppStyle.STATUS_INFO)
                    self.after(1000, lambda: self._poll_lane_status_out(lane, student_info, retries - 1))
                elif status == "pending":
                    self.lbl_cam_status.configure(
                        text=f"⏳ Chờ ESP32 chụp ảnh... ({retries}s)",
                        text_color=AppStyle.WARNING
                    )
                    self.after(1000, lambda: self._poll_lane_status_out(lane, student_info, retries - 1))
                else:
                    self._waiting = False
                    self._on_api_result_out(data, student_info)
            finally:
                if retries <= 0:
                    self._waiting = False

        threading.Thread(target=lambda: self.main_app.run_in_main_thread(_do_poll), daemon=True).start()

    def _on_api_result_out(self, data: dict, student_info: dict):
        """Xử lý kết quả từ API /lane-status cho luồng RA."""
        self._waiting = False
        code = data.get("code", 0)
        msg = data.get("message", "")
        image_path = data.get("image_path", "")

        if code == 200:
            self.lbl_cam_status.configure(text=f"🟢 {msg}", text_color=AppStyle.STATUS_OK)
            self._show_auto_close_popup(msg, "green", 3000)
            score = data.get("score", 100)
            plate = data.get("plate", "")
            fee = data.get("fee", 0)
            surcharge = data.get("surcharge", 0)
            hours_parked = data.get("hours_parked", 0)
            time_in_str = data.get("time_in", "") or data.get("time_in_str", "")
            # Lấy thời gian vào từ preview đã lưu nếu API không trả về
            if not time_in_str:
                time_in_str = getattr(self, "_preview_time_in", "") or ""
            result = {
                "ok": True, "message": msg, "fee": fee,
                "matched_plate": plate, "plate_score": score,
                "fee_info": {"total": fee, "base_fee": fee - surcharge, "surcharge": surcharge,
                             "hours_parked": hours_parked, "time_in_str": time_in_str},
                "student": student_info,
            }
            self._update_result_labels(result, student_info)
            # Mở barie SG90 (5-7s) khi xe ra thành công qua API
            from ..utils.hardware import open_barrier_sync
            threading.Thread(target=open_barrier_sync, daemon=True).start()
            if callable(self.on_updated):
                self.on_updated()
        elif code == 403:
            self._start_blink_warning()
            self._show_status_alert(f"🚨 {msg}", "red", timeout=3000)
        elif code == 402:
            self._show_status_alert(f"💸 {msg}", "orange", timeout=3000)
        elif code == 406:
            score = data.get("score", 0)
            self._show_status_alert(f"⚠️ Không khớp biển số! (Độ tin cậy: {score}%)", "orange", timeout=3000)
        else:
            self._show_status_alert(f"⛔ {msg}", "red", timeout=3000)

    def _fallback_local_outbound(self, student_info, active_tx, preview_plate):
        """Fallback: Xử lý xe ra local khi server API không khả dụng."""
        self.lbl_cam_status.configure(text="🟠 Server API offline — dùng chế độ local...", text_color=AppStyle.WARNING)

        def _exit_hardware_and_vision():
            try:
                from ..utils.hardware import request_esp32_capture, trigger_ir_sensor

                trigger_ir_sensor("out")
                request_esp32_capture("out")

                frame = self.local_cam.get_latest_frame()
                if frame is None:
                    self.main_app.run_in_main_thread(
                        lambda: self._show_status_alert("📷 Không lấy được ảnh từ Camera ra.", "red", timeout=3000)
                    )
                    self.main_app.run_in_main_thread(lambda: setattr(self, "_waiting", False))
                    return

                plate_captured = self.ent_plate.get().strip()
                if not plate_captured:
                    self.main_app.run_in_main_thread(
                        lambda: self._show_status_alert("⚠ Không đọc được biển số lúc ra. Vui lòng chụp lại ảnh.", "orange", timeout=3000)
                    )
                    self.main_app.run_in_main_thread(lambda: setattr(self, "_waiting", False))
                    return

                from thefuzz import fuzz

                best_score = 0
                matched_plate = active_tx.get("BienSo") or active_tx.get("bien_so") or preview_plate

                if matched_plate:
                    best_score = fuzz.ratio(plate_captured.upper(), matched_plate.upper())

                from smart_parking.config import FUZZY_THRESHOLD

                if best_score >= FUZZY_THRESHOLD:
                    res = process_exit(self._current_code, plate_captured, "")
                    self.main_app.run_in_main_thread(lambda: self._on_exit_finished(res, best_score, matched_plate))
                else:
                    self._retry_count += 1
                    if self._retry_count <= 3:
                        self.main_app.run_in_main_thread(lambda s=best_score: self._schedule_retry(s))
                    else:
                        self.main_app.run_in_main_thread(
                            lambda: self._show_status_alert(
                                "🚨 Nhận diện thất bại 3 lần. Dùng Mở Barie Thủ Công nếu cần!",
                                "red",
                                timeout=3000,
                            )
                        )
                        self.main_app.run_in_main_thread(lambda: setattr(self, "_waiting", False))
            except Exception as exc:
                self.main_app.run_in_main_thread(
                    lambda e=exc: self._show_status_alert(f"⛔ Lỗi xử lý xe ra: {e}", "red", timeout=3000)
                )
                self.main_app.run_in_main_thread(lambda: setattr(self, "_waiting", False))

        threading.Thread(target=_exit_hardware_and_vision, daemon=True).start()

    def _show_auto_close_popup(self, message: str, color_type: str = "orange", duration: int = 3000):
        """Hiện popup tự đóng sau `duration` ms. Dùng CTkToplevel + .after() — không blocking."""
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

        self._active_popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 250
        y = self.winfo_y() + (self.winfo_height() // 2) - 110
        self._active_popup.geometry(f"+{int(x)}+{int(y)}")

        main_frame = ctk.CTkFrame(self._active_popup, fg_color=AppStyle.CARD_BG, corner_radius=15, border_width=2, border_color=color)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(main_frame, text=icon, font=("Helvetica", 40)).pack(pady=(15, 5))
        ctk.CTkLabel(main_frame, text=message, font=("Helvetica", 15, "bold"), text_color=AppStyle.TEXT_PRIMARY, wraplength=440).pack(expand=True, padx=20, pady=10)

        # Tự đóng sau duration ms
        self._active_popup.after(duration, lambda: self._active_popup.destroy() if self._active_popup and self._active_popup.winfo_exists() else None)

    def _format_time_value(self, value):
        if not value:
            return "-"
        if isinstance(value, datetime):
            return value.strftime("%H:%M %d/%m/%Y")
        try:
            return datetime.fromisoformat(str(value)).strftime("%H:%M %d/%m/%Y")
        except Exception:
            return str(value)

    def _show_outbound_preview(self, student_info: dict, active_tx: dict | None, matched_plate: str):
        so_du = int(student_info.get("so_du", 0) or 0)
        # Lưu số dư trước khi trừ phí để hiển thị chính xác
        self._balance_before = so_du
        raw_time_in = (active_tx or {}).get("ThoiGianVao") or (active_tx or {}).get("time_in")
        time_in = self._format_time_value(raw_time_in)
        # Lưu lại thời gian vào để dùng khi API trả kết quả
        self._preview_time_in = str(raw_time_in) if raw_time_in else ""
        plate_text = matched_plate or (student_info.get("vehicles", [{}])[0].get("bien_so", "-") if student_info.get("vehicles") else "-")

        self.res_name.configure(text=student_info.get("ho_ten", "-") or "-")
        self.res_id.configure(text=student_info.get("ma_sv", "-") or "-")
        self.res_plate.configure(text=plate_text or "-", text_color=AppStyle.STATUS_INFO)
        self.res_score.configure(text="Đang tính...", text_color=AppStyle.TEXT_SECONDARY)
        self.res_time_in.configure(text=time_in)
        self.res_balance.configure(text=f"{so_du:,}đ")
        self.res_fee.configure(text="Đang tính...", text_color=AppStyle.TEXT_SECONDARY)
        self.res_surcharge.configure(text="Đang tính...", text_color=AppStyle.TEXT_SECONDARY)
        self.res_remain.configure(text="-", text_color=AppStyle.TEXT_SECONDARY)
        self.res_time.configure(text=datetime.now().strftime("%H:%M  %d/%m/%Y"), text_color=AppStyle.STATUS_INFO)
        self.res_decision.configure(text="⏳ ĐANG ĐỐI SOÁT", text_color=AppStyle.WARNING)

        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert(
            "1.0",
            "\n".join(
                [
                    "Trạng thái: Đang đối soát",
                    f"Họ tên: {student_info.get('ho_ten', '-')}",
                    f"MSSV: {student_info.get('ma_sv', '-')}",
                    f"Biển số dự kiến: {plate_text}",
                    f"Thời gian vào: {time_in}",
                    f"Số dư hiện tại: {so_du:,}đ",
                ]
            ),
        )
        self.result_box.configure(state="disabled")
        self._load_entry_image(plate_text)
        self.lbl_cam_status.configure(text="🟡 Hồ sơ đã hiển thị, đang đối soát ảnh...", text_color=AppStyle.WARNING)
        self.update_idletasks()

    def _manual_override_dialog(self):
        if not getattr(self, "_current_code", "").strip():
            self._show_status_alert("⛔ Chưa có mã để mở thủ công.", "red", timeout=3000)
            return

        password = simpledialog.askstring("Mở Barie Thủ Công", "Nhập mật khẩu Admin:", show="*")
        if password is None:
            return

        if password != ADMIN_OVERRIDE_PASSWORD:
            append_security_audit("MANUAL_OVERRIDE", self._current_code, "DENIED", "Sai mật khẩu Admin")
            self._show_status_alert("⛔ Sai mật khẩu Admin.", "red", timeout=3000)
            return

        if self._waiting:
            self._show_status_alert("⛔ Hệ thống đang xử lý một lượt xe ra khác.", "orange", timeout=3000)
            return

        self._waiting = True
        self.lbl_cam_status.configure(text="🟠 Đang mở barie thủ công...", text_color=AppStyle.WARNING)
        threading.Thread(target=self._run_manual_override, daemon=True).start()

    def _run_manual_override(self):
        try:
            from ..utils.hardware import request_esp32_capture, trigger_ir_sensor

            trigger_ir_sensor("out")
            request_esp32_capture("out")

            plate = self.ent_plate.get().strip()
            if not plate and getattr(self, "_current_code", "").strip():
                plate = self._current_code

            res = process_exit(self._current_code, plate, "", force=True, manual_note="Mở thủ công")
            self.main_app.run_in_main_thread(lambda r=res: self._on_exit_finished(r, r.get("plate_score", 0), r.get("matched_plate", plate)))
        except Exception as exc:
            self.main_app.run_in_main_thread(
                lambda e=exc: self._show_status_alert(f"⛔ Lỗi mở thủ công: {e}", "red", timeout=3000)
            )
            self.main_app.run_in_main_thread(lambda: setattr(self, "_waiting", False))

    def _schedule_retry(self, score):
        self.lbl_cam_status.configure(text=f"⚠️ Không khớp biển số! (Độ tin cậy: {score}%). Thử lại {self._retry_count}/3...", text_color=AppStyle.WARNING)
        self.after(3000, lambda: self._fallback_local_outbound(None, None, None))

    def _on_exit_finished(self, res, score, plate):
        self._waiting = False
        if res.get("ok"):
            if res.get("manual"):
                self.lbl_cam_status.configure(text="🟢 Mở thủ công thành công. Barie đang mở.", text_color=AppStyle.STATUS_OK)
            else:
                self.lbl_cam_status.configure(text="🟢 Xe ra thành công. Barie đang mở.", text_color=AppStyle.STATUS_OK)
            # Gửi request mở Barie (sync wrapper cho GUI thread)
            from ..utils.hardware import open_barrier_sync
            threading.Thread(target=open_barrier_sync, daemon=True).start()
            
            self._update_result_labels(res, res.get("student", {}))
            self._show_auto_close_popup(res.get("message", "Xe ra thành công."), "green", 3000)
            if callable(self.on_updated): self.on_updated()
        else:
            self._show_status_alert(res.get("message", "Lỗi"), "red")


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
        self.main_app.run_in_main_thread(lambda p=payload: self._apply_detection(p))

    def _apply_detection(self, payload: dict):
        dtype = str(payload.get("type", "")).lower()
        value = str(payload.get("value", "")).strip()
        conf = float(payload.get("confidence", 0) or 0)
        src = payload.get("source", "-")
        if not value: return
        
        # Cập nhật trạng thái quét
        self.lbl_cam_status.configure(text=f"⬤ [{src}] {dtype.upper()}: {value} ({conf:.0f}%)", text_color=AppStyle.STATUS_INFO)
        
        if dtype == "plate" and conf >= 45.0:
            if self.ent_plate.get().strip().upper() != value.upper():
                self.ent_plate.delete(0, "end")
                self.ent_plate.insert(0, value)
        if dtype in ("refc", "qr", "barcode") and conf >= 70.0:
            self._on_barcode(value)

    # ── Auto process exit ───────────────────────────────────────────────────
    def _auto_process_exit(self, full_code: str = None):
        bc = full_code or getattr(self, "_last_scanned_code", self.ent_barcode.get().strip())
        if bc: self._execute_outbound_protocol(bc)

    def _process_after_stable(self):
        # Đã được tích hợp vào _execute_outbound_protocol
        pass

    def _on_exit_result(self, result: dict, saved_path, plate):
        # Đã được tích hợp vào _on_exit_finished
        pass

    # ── Re-scan ─────────────────────────────────────────────────────────────
    def _schedule_rescan(self):
        # Đã được tích hợp vào _schedule_retry
        pass

    def _do_rescan(self):
        pass

    # ── Blink warning (xe bị khóa) ───────────────────────────────────────────
    def _start_blink_warning(self):
        self._stop_blink_warning()
        self._blink_state = False
        self._blink_count = 0
        self._do_blink()

    def _do_blink(self):
        if not self.winfo_exists(): return
        if self._blink_count >= 20: 
            self._stop_blink_warning()
            return
        self._blink_state = not self._blink_state
        self._blink_count += 1
        color = AppStyle.DANGER if self._blink_state else "#7F1D1D"
        self.warn_frame.configure(fg_color=color)
        self._blink_job = self.after(500, self._do_blink)

    def _stop_blink_warning(self):
        if self._blink_job:
            self.after_cancel(self._blink_job)
            self._blink_job = None

    # ── Display images ────────────────────────────────────────────────────────
    def _load_entry_image(self, bien_so: str):
        """Hiển thị ảnh biển số lúc VÀO để đối chiếu."""
        def _task():
            from ..utils.db_local import find_entry_image
            path = find_entry_image(bien_so)
            if path:
                self.main_app.run_in_main_thread(lambda p=path: self._display_image_on_label(
                    self.img_entry_label, p, 320, 180))
            else:
                self.main_app.run_in_main_thread(
                    lambda: self.img_entry_label.configure(image=None, text="Không tìm thấy ảnh vào"))
        threading.Thread(target=_task, daemon=True).start()



    def _display_image_on_label(self, label, path, max_w, max_h):
        """Load và hiển thị ảnh lên một CTkLabel."""
        try:
            img = Image.open(path).convert("RGB")
            ratio = min(max_w / img.width, max_h / img.height)
            nw = int(img.width * ratio)
            nh = int(img.height * ratio)
            img = img.resize((nw, nh))
            ci = ctk.CTkImage(light_image=img, dark_image=img, size=(nw, nh))
            label.configure(image=ci, text="")
            label.image = ci
        except Exception:
            label.configure(image=None, text="Lỗi hiển thị ảnh")

    # ── Update result labels ──────────────────────────────────────────────────
    def _update_result_labels(self, result: dict, st: dict):
        fee = result.get("fee", 0) or 0
        fee_info = result.get("fee_info") or {}
        # Dùng balance_before đã lưu từ preview (trước khi trừ phí) nếu có
        so_du_before = getattr(self, "_balance_before", None)
        if so_du_before is None:
            so_du_before = int(st.get("so_du", 0) or 0)
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

        # Thời gian vào: ưu tiên fee_info → result → preview đã lưu
        time_in_raw = fee_info.get("time_in_str") or result.get("time_in") or getattr(self, "_preview_time_in", "")
        time_in_display = self._format_time_value(time_in_raw) if time_in_raw else "-"
        self.res_time_in.configure(text=time_in_display)

        # Số dư trước (trước khi trừ phí)
        self.res_balance.configure(text=f"{so_du_before:,}đ")
        self.res_fee.configure(
            text=f"{fee:,}đ" if fee else "-",
            text_color=AppStyle.WARNING)

        # Phụ phí 24h
        surcharge = fee_info.get("surcharge", 0)
        hours = fee_info.get("hours_parked", 0)
        if surcharge > 0:
            self.res_surcharge.configure(
                text=f"+{surcharge:,}đ (đỗ {hours:.1f}h)",
                text_color=AppStyle.DANGER)
        else:
            self.res_surcharge.configure(
                text=f"Không có ({hours:.1f}h)" if hours > 0 else "Không có",
                text_color=AppStyle.TEXT_SECONDARY)

        remain = so_du_before - fee if ok else so_du_before
        self.res_remain.configure(
            text=f"{remain:,}đ",
            text_color=AppStyle.SUCCESS if remain >= 0 else AppStyle.DANGER)

        self.res_time.configure(
            text=datetime.now().strftime("%H:%M  %d/%m/%Y"),
            text_color=AppStyle.STATUS_INFO)

        # Quyết định: Thành công / Từ chối
        if ok:
            dec_text = "✅ THÀNH CÔNG"
        else:
            dec_text = "✖ TỪ CHỐI"
        self.res_decision.configure(
            text=dec_text,
            text_color=AppStyle.SUCCESS if ok else AppStyle.DANGER)

        # Textbox log
        surcharge_text = f"+{surcharge:,}đ" if surcharge > 0 else "Không có"
        lines = [
            f"Trạng thái: {'THÀNH CÔNG' if ok else 'THẤT BẠI'}",
            f"Thông điệp: {result.get('message', '-')}",
            f"Biển số quét: {self.ent_plate.get().strip() or '-'}",
            f"Biển số khớp: {result.get('matched_plate', '-')}",
            f"Điểm khớp: {score}%",
            f"Phí cơ bản: {fee_info.get('base_fee', 0):,}đ",
            f"Phụ phí 24h: {surcharge_text}",
            f"Tổng phí: {fee:,}đ",
            f"Thời gian đỗ: {hours:.1f} giờ",
            f"Số dư trước: {so_du_before:,}đ",
            f"Số dư sau: {remain:,}đ",
            f"Thời gian vào: {time_in_display}",
            f"Thời gian ra: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
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
        self._stop_blink_warning()

    # ── Clear ─────────────────────────────────────────────────────────────────
    def _clear(self):
        self.ent_barcode.delete(0, "end")
        self.ent_plate.delete(0, "end")
        self._last_processed_code = ""
        self._last_processed_ts = 0.0
        self._balance_before = None
        self._preview_time_in = ""
        self._hide_warn()
        if self._rescan_job:
            self.after_cancel(self._rescan_job)
            self._rescan_job = None
        for a in ("res_name", "res_id", "res_plate", "res_score", "res_time_in", "res_balance",
                  "res_fee", "res_surcharge", "res_remain", "res_time", "res_decision"):
            getattr(self, a).configure(text="-", text_color=AppStyle.TEXT_PRIMARY)
        self.img_entry_label.configure(image=None, text="Chưa có ảnh vào")
        self.img_entry_label.image = None
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", "Chưa có giao dịch xe ra.")
        self.result_box.configure(state="disabled")

    # ── Camera lifecycle ──────────────────────────────────────────────────────
    def start_cameras(self):
        cam_id = int(os.getenv("LAPTOP_CAMERA_ID", "0"))
        self.local_cam.start(camera_id=cam_id)
        self.iot_cam.start()
        self._check_camera_status()

    def _check_camera_status(self):
        """Kiểm tra trạng thái camera (xanh/vàng/đỏ)."""
        if not self.local_cam.base.running: return
        
        now = time.time()
        last_frame = self.local_cam.base.last_frame_ts
        diff = now - last_frame if last_frame > 0 else 999
        
        if diff < 2.0:
            self.lbl_cam_status.configure(text="⬤ Camera xe ra đang hoạt động (Online)", text_color=AppStyle.STATUS_OK)
        elif diff < 10.0:
            self.lbl_cam_status.configure(text=f"⬤ Đang chờ tín hiệu camera ({int(diff)}s)...", text_color=AppStyle.WARNING)
        else:
            self.lbl_cam_status.configure(text="⛔ Lỗi hệ thống: Camera không phản hồi quá 10s!", text_color=AppStyle.DANGER)
            
        self.after(1000, self._check_camera_status)

    def stop_cameras(self):

        self.local_cam.stop()
        self.iot_cam.stop()
        self.lbl_cam_status.configure(
            text="⬤  Camera xe ra đang dừng", text_color=AppStyle.TEXT_MUTED)
        if self._rescan_job:
            self.after_cancel(self._rescan_job)
            self._rescan_job = None
        self._stop_blink_warning()
        self._waiting = False
