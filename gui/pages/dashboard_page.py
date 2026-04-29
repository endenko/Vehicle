from datetime import datetime
import threading
from tkinter import messagebox, ttk

import customtkinter as ctk

if (__package__ or "").startswith("gui"):
    from ..styles import AppStyle
    from ..utils.db_local import (
        export_monthly_history_csv,
        get_active,
        get_stats,
        search_active_transactions,
    )
else:
    from gui.styles import AppStyle
    from gui.utils.db_local import (
        export_monthly_history_csv,
        get_active,
        get_stats,
        search_active_transactions,
    )


class DashboardPage(ctk.CTkFrame):
    def __init__(self, parent, main_app):
        super().__init__(parent, fg_color="transparent")
        self.main_app = main_app
        self._current_keyword = ""
        self._build()
        self.after(1200, self.refresh_data)

    def _build(self):
        shell = ctk.CTkFrame(self, fg_color=AppStyle.CARD_BG, corner_radius=18)
        shell.pack(fill="both", expand=True, padx=10, pady=10)

        hdr = ctk.CTkFrame(shell, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            hdr,
            text="📊  Dashboard",
            font=AppStyle.SUBTITLE_FONT,
            text_color=AppStyle.PRIMARY,
        ).pack(side="left")

        btn_row = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_row.pack(side="right")

        ctk.CTkButton(
            btn_row,
            text="⬇ Xuất file Excel/CSV",
            width=160,
            fg_color=AppStyle.SUCCESS,
            hover_color=AppStyle.SUCCESS_DARK,
            command=self.export_csv,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_row,
            text="⟳  Làm mới",
            width=110,
            fg_color=AppStyle.PRIMARY,
            hover_color=AppStyle.PRIMARY_DARK,
            command=self.refresh_data,
        ).pack(side="right")

        card_row = ctk.CTkFrame(shell, fg_color="transparent")
        card_row.pack(fill="x", padx=12, pady=(0, 10))
        for index in range(3):
            card_row.grid_columnconfigure(index, weight=1)

        self.card_parked = self._build_card(card_row, 0, "🚗 Xe đang đỗ", AppStyle.PRIMARY)
        self.card_exits = self._build_card(card_row, 1, "✅ Lượt ra hôm nay", AppStyle.SUCCESS)
        self.card_revenue = self._build_card(card_row, 2, "💰 Doanh thu hôm nay", AppStyle.WARNING)

        controls = ctk.CTkFrame(shell, fg_color=AppStyle.SURFACE, corner_radius=14)
        controls.pack(fill="x", padx=16, pady=(0, 10))
        controls.grid_columnconfigure(0, weight=1)

        search_row = ctk.CTkFrame(controls, fg_color="transparent")
        search_row.pack(fill="x", padx=12, pady=12)
        search_row.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            search_row,
            placeholder_text="🔍 Nhập Biển số hoặc MSSV để tìm kiếm...",
            height=38,
            fg_color=AppStyle.CARD_BG,
            border_color=AppStyle.BORDER,
            text_color=AppStyle.TEXT_PRIMARY,
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda event: self.apply_filter())

        ctk.CTkButton(
            search_row,
            text="Tìm/Lọc",
            width=110,
            height=38,
            fg_color=AppStyle.PRIMARY,
            hover_color=AppStyle.PRIMARY_DARK,
            command=self.apply_filter,
        ).grid(row=0, column=1, padx=(0, 10))

        ctk.CTkButton(
            search_row,
            text="Xóa bộ lọc",
            width=120,
            height=38,
            fg_color=AppStyle.SURFACE,
            hover_color=AppStyle.BORDER,
            text_color=AppStyle.TEXT_SECONDARY,
            command=self.clear_filter,
        ).grid(row=0, column=2)

        table_shell = ctk.CTkFrame(shell, fg_color=AppStyle.CARD_BG, corner_radius=16)
        table_shell.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        table_shell.grid_rowconfigure(1, weight=1)
        table_shell.grid_columnconfigure(0, weight=1)

        table_hdr = ctk.CTkFrame(table_shell, fg_color="transparent")
        table_hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        ctk.CTkLabel(
            table_hdr,
            text="📋  Xe Đang Đỗ",
            font=AppStyle.SUBTITLE_FONT,
            text_color=AppStyle.PRIMARY,
        ).pack(side="left")

        self.status_label = ctk.CTkLabel(
            table_hdr,
            text="",
            font=AppStyle.SMALL_FONT,
            text_color=AppStyle.TEXT_MUTED,
        )
        self.status_label.pack(side="right")

        tf = ctk.CTkFrame(table_shell, fg_color="transparent")
        tf.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        tf.grid_columnconfigure(0, weight=1)
        tf.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dashboard.Treeview",
            rowheight=28,
            font=("Helvetica", 11),
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground="#1F2937",
        )
        style.configure(
            "Dashboard.Treeview.Heading",
            font=("Helvetica", 11, "bold"),
            background="#EEF2F7",
            foreground="#3B5998",
        )
        style.map(
            "Dashboard.Treeview",
            background=[("selected", "#3B82F6")],
            foreground=[("selected", "white")],
        )

        cols = ("ID", "Biển số", "Họ tên", "MSSV", "Lớp", "Khoa", "Giờ vào", "Trạng thái")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", style="Dashboard.Treeview", height=16)
        widths = [60, 110, 160, 95, 90, 120, 145, 95]
        for col, width in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center", width=width, stretch=False)

        sy = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        sx = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")

    def _build_card(self, parent, col, title, accent):
        card = ctk.CTkFrame(
            parent,
            fg_color=AppStyle.CARD_BG,
            corner_radius=16,
            border_width=1,
            border_color=AppStyle.BORDER,
        )
        card.grid(row=0, column=col, padx=8, pady=4, sticky="nsew")

        ctk.CTkLabel(card, text=title, font=AppStyle.BODY_BOLD, text_color=accent).pack(anchor="w", padx=16, pady=(14, 4))
        value_label = ctk.CTkLabel(card, text="0", font=("Helvetica", 32, "bold"), text_color=AppStyle.TEXT_PRIMARY)
        value_label.pack(anchor="w", padx=16)
        ctk.CTkLabel(card, text="Hôm nay", font=AppStyle.SMALL_FONT, text_color=AppStyle.TEXT_MUTED).pack(anchor="w", padx=16, pady=(0, 14))
        return value_label

    def refresh_data(self, keyword: str = None):
        keyword = self.search_entry.get().strip() if keyword is None else (keyword or "").strip()
        self._current_keyword = keyword

        def _task():
            try:
                stats = get_stats() or {}
                if keyword:
                    active = search_active_transactions(keyword, 200) or []
                else:
                    active = get_active(200) or []
                self.main_app.run_in_main_thread(lambda: self._update_ui(stats, active, keyword))
            except Exception as e:
                print(f"[Dashboard] Lỗi tải dữ liệu: {e}")

        threading.Thread(target=_task, daemon=True).start()

    def apply_filter(self):
        self.refresh_data(self.search_entry.get())

    def clear_filter(self):
        self.search_entry.delete(0, "end")
        self.refresh_data("")

    def export_csv(self):
        def _task():
            try:
                path = export_monthly_history_csv()
                if path:
                    self.main_app.run_in_main_thread(
                        lambda p=path: messagebox.showinfo("Xuất báo cáo", f"Đã xuất file CSV:\n{p}")
                    )
                else:
                    self.main_app.run_in_main_thread(
                        lambda: messagebox.showwarning("Xuất báo cáo", "Không có dữ liệu trong tháng hiện tại.")
                    )
            except Exception as e:
                self.main_app.run_in_main_thread(lambda: messagebox.showerror("Xuất báo cáo", str(e)))

        threading.Thread(target=_task, daemon=True).start()

    def _update_ui(self, stats, active, keyword: str):
        self.card_parked.configure(text=str(stats.get("parked_count", 0)))
        self.card_exits.configure(text=str(stats.get("exits_today", 0)))
        rev = int(stats.get("revenue_today", 0) or 0)
        self.card_revenue.configure(text=f"{rev:,} VNĐ")

        for row in self.tree.get_children():
            self.tree.delete(row)

        for item in active:
            self.tree.insert(
                "",
                "end",
                values=(
                    item.get("transaction_id", "-"),
                    item.get("license_plate", "-"),
                    item.get("owner_name", "-"),
                    item.get("owner_identity", "-"),
                    item.get("owner_class", "-"),
                    item.get("owner_major", "-"),
                    self._fmt(item.get("time_in")),
                    item.get("status", "-"),
                ),
            )

        if keyword:
            self.status_label.configure(text=f"Đang lọc: {keyword} | {len(active)} kết quả")
        else:
            self.status_label.configure(text=f"Hiển thị {len(active)} xe đang đỗ")

    def _fmt(self, value):
        if not value:
            return "-"
        if isinstance(value, datetime):
            return value.strftime("%H:%M %d/%m/%Y")
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).strftime("%H:%M %d/%m/%Y")
            except Exception:
                return value
        return str(value)
