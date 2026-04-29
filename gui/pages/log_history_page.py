# gui/pages/log_history_page.py
from datetime import datetime
import threading
from tkinter import ttk
import customtkinter as ctk

if (__package__ or "").startswith("gui"):
    from ..styles import AppStyle
    from ..utils.db_local import get_history
else:
    from gui.styles import AppStyle
    from gui.utils.db_local import get_history


class LogHistoryPage(ctk.CTkFrame):
    def __init__(self, parent, main_app):
        super().__init__(parent, fg_color="transparent")
        self.main_app = main_app
        self._build()

    def _build(self):
        c = ctk.CTkFrame(self, fg_color=AppStyle.CARD_BG, corner_radius=14)
        c.pack(fill="both", expand=True, padx=10, pady=10)

        hdr = ctk.CTkFrame(c, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(14, 8))
        ctk.CTkLabel(hdr, text="📋  Lịch Sử Vào Ra",
                     font=AppStyle.SUBTITLE_FONT,
                     text_color=AppStyle.PRIMARY).pack(side="left")
        ctk.CTkButton(hdr, text="⟳  Làm mới", width=110,
                      fg_color=AppStyle.PRIMARY, hover_color=AppStyle.PRIMARY_DARK,
                      command=self.refresh_data).pack(side="right")

        cols = ("ID","Biển số","Họ tên","MSSV","Lớp","Khoa",
                "Giờ vào","Giờ ra","Trạng thái","Phí")
        tf = ctk.CTkFrame(c, fg_color="transparent")
        tf.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        tf.grid_columnconfigure(0, weight=1)
        tf.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.Treeview",
                        background="#1E293B", fieldbackground="#1E293B",
                        foreground="#F1F5F9", rowheight=28,
                        font=("Helvetica", 11))
        style.configure("Dark.Treeview.Heading",
                        background="#0F172A", foreground="#94A3B8",
                        font=("Helvetica", 11, "bold"))
        style.map("Dark.Treeview",
                  background=[("selected", "#3B82F6")],
                  foreground=[("selected", "white")])

        self.tree = ttk.Treeview(tf, columns=cols, show="headings",
                                 style="Dark.Treeview", height=20)
        widths = [50,110,160,100,80,100,130,130,90,80]
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center", width=w)

        sy = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        sx = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")

        self.status = ctk.CTkLabel(c, text="", font=AppStyle.SMALL_FONT,
                                   text_color=AppStyle.TEXT_MUTED)
        self.status.pack(anchor="w", padx=14, pady=(0, 6))

    def refresh_data(self):
        def _task():
            try:
                history = get_history(limit=500)
                self.main_app.run_in_main_thread(lambda: self._update_ui(history))
            except Exception as e:
                print(f"[LogHistory] Lỗi tải dữ liệu: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def _update_ui(self, history):
        if history is None:
            self.status.configure(text="Không thể lấy dữ liệu.")
            return
        for row in self.tree.get_children():
            self.tree.delete(row)
        for item in history:
            self.tree.insert("", "end", values=(
                item.get("transaction_id", "-"),
                item.get("license_plate", "-"),
                item.get("owner_name", "-"),
                item.get("owner_identity", "-"),
                item.get("owner_class", "-"),
                item.get("owner_major", "-"),
                self._fmt(item.get("time_in")),
                self._fmt(item.get("time_out")),
                item.get("status", "-"),
                f"{int(item.get('fee') or 0):,}đ" if item.get("fee") else "-",
            ))
        self.status.configure(text=f"Đã tải {len(history)} bản ghi.")

    def _fmt(self, v):
        if not v: return "-"
        if isinstance(v, datetime): return v.strftime("%H:%M:%S %d/%m/%Y")
        if isinstance(v, str):
            try: return datetime.fromisoformat(v).strftime("%H:%M:%S %d/%m/%Y")
            except: return v
        return str(v)
