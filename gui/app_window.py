from datetime import datetime
import subprocess
import sys
import threading
import queue
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

if (__package__ or "").startswith("gui"):
    from .pages.dashboard_page import DashboardPage
    from .pages.log_history_page import LogHistoryPage
    from .pages.xe_ra_page import XeRaPage
    from .pages.xe_vao_page import XeVaoPage
    from .styles import AppStyle
else:
    from pages.dashboard_page import DashboardPage
    from pages.log_history_page import LogHistoryPage
    from pages.xe_ra_page import XeRaPage
    from pages.xe_vao_page import XeVaoPage
    from styles import AppStyle

BASE_DIR = Path(__file__).resolve().parent.parent


class MainApp(ctk.CTk):
    def __init__(self):
        print("[GUI] Đang khởi tạo MainApp...")
        super().__init__()
        self.ui_queue = queue.Queue()  # Hàng đợi xử lý UI an toàn
        AppStyle.apply()
        print("[GUI] Đã áp dụng Style.")
        self.title("School Parking Management")
        self.geometry("1280x800")
        self.minsize(1024, 720)
        self.configure(fg_color=AppStyle.APP_BG)

        # ── Header ────────────────────────────────────────────────────────────
        self.header = ctk.CTkFrame(self, height=64, fg_color=AppStyle.PRIMARY)
        self.header.pack(fill="x", padx=0, pady=0)
        self.header.pack_propagate(False)

        # Logo + Title
        logo_frame = ctk.CTkFrame(self.header, fg_color="transparent")
        logo_frame.pack(side="left", padx=(20, 0))

        ctk.CTkLabel(
            logo_frame,
            text="SPM",
            font=("Helvetica", 24, "bold"),
            text_color="white",
        ).pack(side="left", padx=(16, 8))

        divider = ctk.CTkLabel(
            logo_frame, text="│", font=("Helvetica", 24), text_color="#94A3B8"
        )
        divider.pack(side="left", padx=4)

        ctk.CTkLabel(
            logo_frame,
            text="School Parking Management",
            font=("Helvetica", 21, "bold"),
            text_color="white",
        ).pack(side="left")

        # Right side buttons
        self.time_label = ctk.CTkLabel(self.header, text="", font=("Helvetica", 14), text_color="white")
        self.time_label.pack(side="right", padx=20)
        self._update_time()

        ctk.CTkButton(
            self.header,
            text="🚨 Báo động",
            fg_color=AppStyle.DANGER,
            hover_color="#dc2626",
            width=120,
            command=self.show_alert,
        ).pack(side="right", padx=8)

        # Nút Quản lý (mở run_generate.py)
        ctk.CTkButton(
            self.header,
            text="⚙ Quản lý",
            fg_color="#6366F1",
            hover_color="#4F46E5",
            width=120,
            command=self._open_manager,
        ).pack(side="right", padx=8)

        # ── Tab View ──────────────────────────────────────────────────────────
        self.tabview = ctk.CTkTabview(self, fg_color=AppStyle.APP_BG)
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(10, 12))

        self.tabview.add("Xe Vao")
        self.tabview.add("Xe Ra")
        self.tabview.add("Log History")
        self.tabview.add("Thong Tin")

        # Cập nhật tab colors (Yêu cầu 6: hài hòa hơn)
        try:
            self.tabview._segmented_button.configure(
                fg_color=AppStyle.TAB_INACTIVE,
                selected_color=AppStyle.TAB_ACTIVE,
                selected_hover_color=AppStyle.TAB_ACTIVE_HOVER,
                unselected_color=AppStyle.TAB_INACTIVE,
                unselected_hover_color=AppStyle.TAB_INACTIVE_HOVER,
                text_color="white",
                text_color_disabled=AppStyle.TEXT_MUTED,
            )
        except Exception:
            pass

        # ── Pages ─────────────────────────────────────────────────────────────
        self.xe_vao_page = XeVaoPage(
            self.tabview.tab("Xe Vao"),
            self,
            on_transaction_updated=self._refresh_data_views,
        )
        self.xe_vao_page.pack(fill="both", expand=True)

        self.xe_ra_page = XeRaPage(
            self.tabview.tab("Xe Ra"),
            self,
            on_transaction_updated=self._refresh_data_views,
        )
        self.xe_ra_page.pack(fill="both", expand=True)

        self.log_history_page = LogHistoryPage(self.tabview.tab("Log History"), self)
        self.log_history_page.pack(fill="both", expand=True)

        self.dashboard_page = DashboardPage(self.tabview.tab("Thong Tin"), self)
        self.dashboard_page.pack(fill="both", expand=True)

        # Chờ 1.5s mới tải dữ liệu để tránh lỗi "main thread is not in main loop"
        self.after(1500, self._refresh_data_views)
        self.xe_ra_page.stop_cameras()

        self._active_tab = self.tabview.get()
        self._alert_blink_state = False
        self.after(250, self._watch_tab_change)
        self.after(0, self._ensure_visible)

        # KHỞI ĐỘNG CAMERA SAU KHI GUI ĐÃ HIỆN LÊN
        print("[GUI] Đang đợi giao diện hiển thị để khởi động Camera...")
        self.after(1200, lambda: self.xe_vao_page.start_cameras())

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        print("[GUI] Khởi tạo MainApp hoàn tất.")
        self._process_ui_queue()  # Bắt đầu quét hàng đợi

    def run_in_main_thread(self, task):
        """Đẩy một tác vụ vào luồng chính để xử lý UI an toàn"""
        self.ui_queue.put(task)

    def _process_ui_queue(self):
        """Xử lý các tác vụ UI từ hàng đợi"""
        try:
            while True:
                task = self.ui_queue.get_nowait()
                task()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(50, self._process_ui_queue)  # Quét lại sau 50ms

    def _ensure_visible(self):
        print("[GUI] Yêu cầu hiển thị cửa sổ (Hyprland safe)...")
        try:
            self.deiconify()
        except Exception as e:
            print(f"[GUI] Lỗi hiển thị cửa sổ: {e}")

    # ── Open Manager subprocess ───────────────────────────────────────────────
    def _open_manager(self):
        """Mở run_generate.py như một subprocess độc lập."""
        manager_path = BASE_DIR / "run_generate.py"
        if not manager_path.exists():
            messagebox.showerror("Lỗi", f"Không tìm thấy: {manager_path}")
            return
        try:
            subprocess.Popen(
                [sys.executable, str(manager_path)],
                cwd=str(BASE_DIR),
            )
            print(f"[GUI] Đã mở Manager: {manager_path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể mở Manager: {e}")

    # ── Data refresh (Run in background to prevent hang) ───────────────────
    def _refresh_data_views(self):
        print("[Data] Đang làm mới dữ liệu từ bối cảnh (background)...")

        def _refresh_task():
            try:
                for page in (self.log_history_page, self.dashboard_page):
                    refresh = getattr(page, "refresh_data", None)
                    if callable(refresh):
                        refresh()
                print("[Data] Đã làm mới dữ liệu xong.")
            except Exception as e:
                print(f"[Data] Lỗi làm mới dữ liệu: {e}")

        threading.Thread(target=_refresh_task, daemon=True).start()

    # ── Tab change watch ────────────────────────────────────────────────────
    def _watch_tab_change(self):
        if not self.winfo_exists():
            return

        current_tab = self.tabview.get()
        if current_tab != self._active_tab:
            self._handle_tab_change(current_tab)
            self._active_tab = current_tab

        self.after(250, self._watch_tab_change)

    def _handle_tab_change(self, current_tab: str):
        if current_tab == "Xe Ra":
            self.xe_ra_page.stop_cameras()
            self.xe_vao_page.begin_exit_transition(3, on_complete=self.xe_ra_page.start_cameras)
            return

        self.xe_vao_page.cancel_transition()
        self.xe_ra_page.stop_cameras()
        if current_tab == "Xe Vao":
            self.xe_vao_page.start_cameras()
        else:
            self.xe_vao_page.stop_cameras()

    # ── Close ───────────────────────────────────────────────────────────────
    def _on_close(self):
        try:
            self.xe_vao_page.cancel_transition()
            self.xe_vao_page.stop_cameras()
            self.xe_ra_page.stop_cameras()
        finally:
            self.destroy()

    # ── Clock ───────────────────────────────────────────────────────────────
    def _update_time(self):
        self.time_label.configure(text=datetime.now().strftime("%H:%M:%S | %d/%m/%Y"))
        self.after(1000, self._update_time)

    # ── Alert ───────────────────────────────────────────────────────────────
    def show_alert(self):
        messagebox.showwarning("🚨 Báo động", "Đã gửi tín hiệu báo động cho bộ phận bảo vệ.")