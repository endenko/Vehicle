# gui/pages/dashboard_page.py
from datetime import datetime
import threading
from tkinter import ttk
import customtkinter as ctk

if (__package__ or "").startswith("gui"):
    from ..styles import AppStyle
    from ..utils.db_local import get_active, get_stats
else:
    from gui.styles import AppStyle
    from gui.utils.db_local import get_active, get_stats


class DashboardPage(ctk.CTkFrame):
    def __init__(self, parent, main_app):
        super().__init__(parent, fg_color="transparent")
        self.main_app = main_app
        self._build()
        # Chờ 2s mới bắt đầu tự động làm mới
        self.after(2000, self._auto_refresh)

    def _build(self):
        # Summary cards
        card_row = ctk.CTkFrame(self, fg_color="transparent")
        card_row.pack(fill="x", padx=14, pady=(14, 8))
        for i in range(3):
            card_row.grid_columnconfigure(i, weight=1)

        self.card_parked   = self._card(card_row, "🚗 Xe đang đỗ", "0", 0)
        self.card_exits    = self._card(card_row, "✅ Lượt ra hôm nay", "0", 1)
        self.card_revenue  = self._card(card_row, "💰 Doanh thu hôm nay", "0đ", 2)

        # Fee info & Warning
        fee_f = ctk.CTkFrame(self, fg_color=AppStyle.CARD_BG, corner_radius=12)
        fee_f.pack(fill="x", padx=14, pady=(0, 8))
        
        # Dòng biểu phí gốc
        ctk.CTkLabel(fee_f,
                     text="🕐 Phí gửi xe:  6:00–17:30 → 2,000đ   |   17:30–23:00 → 3,000đ   |   23:00–6:00 → ⛔ Không nhận",
                     font=AppStyle.BODY_FONT, text_color=AppStyle.TEXT_SECONDARY
                     ).pack(padx=14, pady=(8, 2)) # Chỉnh lại pady để nhường chỗ cho dòng dưới
        
        # Dòng cảnh cáo mới
        ctk.CTkLabel(fee_f,
                     text="⚠️ Cảnh báo: Xe lưu bãi quá 24 giờ sẽ bị cộng thêm phụ phí 5,000đ!",
                     font=AppStyle.BODY_FONT, text_color="#ef4444" # Sử dụng mã màu đỏ cảnh báo
                     ).pack(padx=14, pady=(0, 8))
        # Active table
        tbl = ctk.CTkFrame(self, fg_color=AppStyle.CARD_BG, corner_radius=14)
        tbl.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        tbl.grid_rowconfigure(1, weight=1)
        tbl.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(tbl, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        ctk.CTkLabel(hdr, text="📋  Xe Đang Đỗ",
                     font=AppStyle.SUBTITLE_FONT,
                     text_color=AppStyle.PRIMARY).pack(side="left")
        ctk.CTkButton(hdr, text="⟳  Làm mới", width=110,
                      fg_color=AppStyle.PRIMARY, hover_color=AppStyle.PRIMARY_DARK,
                      command=self.refresh_data).pack(side="right")

        tf = ctk.CTkFrame(tbl, fg_color="transparent")
        tf.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        tf.grid_columnconfigure(0, weight=1)
        tf.grid_rowconfigure(0, weight=1)

        cols = ("ID","Biển số","Họ tên","MSSV","Lớp","Khoa","Giờ vào","Trạng thái")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings",
                                 style="Light.Treeview", height=14)
        widths = [50,110,160,100,80,100,140,90]
        
        # CHÚ Ý: Phải thêm stretch=False để khóa độ rộng cột, bắt buộc thanh cuộn phải hoạt động
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center", width=w, stretch=False)

        # Lắp đặt thanh cuộn dọc (đã có)
        sy = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        
        # Bổ sung thanh cuộn ngang
        sx = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)

        # Tích hợp cả hai hệ thống cuộn vào Treeview
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

        # Phân bổ vị trí trên lưới (Grid)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew") # Thanh cuộn ngang nằm dưới đáy

    def _card(self, parent, title, val, col):
        c = ctk.CTkFrame(parent, fg_color=AppStyle.CARD_BG, corner_radius=14)
        c.grid(row=0, column=col, padx=8, pady=4, sticky="nsew")
        ctk.CTkLabel(c, text=title, font=AppStyle.BODY_FONT,
                     text_color=AppStyle.TEXT_SECONDARY).pack(pady=(14, 4))
        lbl = ctk.CTkLabel(c, text=val, font=("Helvetica", 30, "bold"),
                            text_color=AppStyle.PRIMARY)
        lbl.pack(pady=(0, 14))
        return lbl

    def refresh_data(self):
        def _task():
            try:
                stats = get_stats() or {}
                active = get_active(200) or []
                self.main_app.run_in_main_thread(lambda: self._update_ui(stats, active))
            except Exception as e:
                print(f"[Dashboard] Lỗi tải dữ liệu: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def _update_ui(self, stats, active):
        self.card_parked.configure(text=str(stats.get("parked_count", 0)))
        self.card_exits.configure(text=str(stats.get("exits_today", 0)))
        rev = stats.get("revenue_today", 0) or 0
        self.card_revenue.configure(text=f"{int(rev):,}đ")

        for row in self.tree.get_children():
            self.tree.delete(row)
        for item in active:
            self.tree.insert("", "end", values=(
                item.get("transaction_id", "-"),
                item.get("license_plate", "-"),
                item.get("owner_name", "-"),
                item.get("owner_identity", "-"),
                item.get("owner_class", "-"),
                item.get("owner_major", "-"),
                self._fmt(item.get("time_in")),
                item.get("status", "-"),
            ))

    def _auto_refresh(self):
        self.refresh_data()
        self.after(30_000, self._auto_refresh)

    def _fmt(self, v):
        if not v: return "-"
        if isinstance(v, datetime): return v.strftime("%H:%M %d/%m/%Y")
        if isinstance(v, str):
            try: return datetime.fromisoformat(v).strftime("%H:%M %d/%m/%Y")
            except: return v
        return str(v)
