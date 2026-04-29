#!/usr/bin/env python3
"""
run_generate.py — GUI Manager: Quản lý Dữ liệu Sinh viên & Sinh mã QR/Barcode
Chạy độc lập:  python run_generate.py
Database:       smart_parking.db (SQLite)
"""
import os
import sys
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import ttk, messagebox

import customtkinter as ctk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DB_PATH = BASE_DIR / "smart_parking.db"
SCHEMA_PATH = BASE_DIR / "schema_sqlite.sql"
BARCODES_DIR = BASE_DIR / "createbarcode" / "barcodes"


# ── Database helper ──────────────────────────────────────────────────────────
def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_db():
    """Khởi tạo DB nếu chưa có bảng."""
    if not DB_PATH.exists() and SCHEMA_PATH.exists():
        conn = _connect()
        with open(str(SCHEMA_PATH), "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()


# ── Style ────────────────────────────────────────────────────────────────────
class _S:
    BG          = "#EEF2F7"
    CARD        = "#FFFFFF"
    SURFACE     = "#F3F6FB"
    PRIMARY     = "#3B5998"
    PRIMARY_DK  = "#2D4373"
    SUCCESS     = "#10B981"
    DANGER      = "#EF4444"
    WARNING     = "#F59E0B"
    PURPLE      = "#7C3AED"
    TEXT        = "#0F172A"
    TEXT2       = "#475569"
    MUTED       = "#64748B"
    BORDER      = "#CBD5E1"
    TITLE       = ("Helvetica", 20, "bold")
    SUBTITLE    = ("Helvetica", 15, "bold")
    BODY        = ("Helvetica", 13)
    BODY_B      = ("Helvetica", 13, "bold")
    SMALL       = ("Helvetica", 11)


# ══════════════════════════════════════════════════════════════════════════════
class GeneratorManagerApp(ctk.CTk):
    """GUI Manager: CRUD Sinh viên + Sinh mã QR/Barcode."""

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.title("⚙ Quản Lý Hệ Thống — SmartParking")
        self.geometry("1300x850")
        self.minsize(1100, 700)
        self.configure(fg_color=_S.BG)

        _ensure_db()

        # Layout: 2 cột
        self.grid_columnconfigure(0, weight=4)
        self.grid_columnconfigure(1, weight=6)
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()
        self.after(300, self._load_data)

    # ── Left Panel: Form + Buttons + Chart ────────────────────────────────────
    def _build_left_panel(self):
        left = ctk.CTkFrame(self, fg_color=_S.CARD, corner_radius=14)
        left.grid(row=0, column=0, padx=(14, 7), pady=14, sticky="nsew")

        ctk.CTkLabel(
            left, text="📝  Thông Tin Sinh Viên",
            font=_S.SUBTITLE, text_color=_S.PRIMARY
        ).pack(anchor="w", padx=20, pady=(20, 10))

        # Form fields
        self.entries = {}
        fields = [
            ("Họ tên:",       "HoTen"),
            ("MSSV:",         "MaSV"),
            ("Biển số:",      "BienSo"),
            ("Lớp:",          "Lop"),
            ("Khoa:",         "Khoa"),
            ("Số dư (đ):",    "SoDu"),
        ]
        for label_text, key in fields:
            row_f = ctk.CTkFrame(left, fg_color="transparent")
            row_f.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row_f, text=label_text, font=_S.BODY, width=100, anchor="w",
                         text_color=_S.TEXT2).pack(side="left")
            ent = ctk.CTkEntry(row_f, fg_color=_S.SURFACE, border_color=_S.BORDER,
                               text_color=_S.TEXT, height=34)
            ent.pack(side="left", fill="x", expand=True)
            self.entries[key] = ent

        # Thêm Combobox cho Trạng thái
        row_state = ctk.CTkFrame(left, fg_color="transparent")
        row_state.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(row_state, text="Trạng thái:", font=_S.BODY, width=100, anchor="w",
                     text_color=_S.TEXT2).pack(side="left")
        self.cmb_state = ctk.CTkComboBox(row_state, values=["Hoạt động", "Khóa", "Chưa có thẻ"],
                                         fg_color=_S.SURFACE, border_color=_S.BORDER,
                                         text_color=_S.TEXT, height=34, state="readonly")
        self.cmb_state.set("Hoạt động")
        self.cmb_state.pack(side="left", fill="x", expand=True)

        # CRUD buttons
        btn_frame = ctk.CTkFrame(left, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkButton(btn_frame, text="➕ Thêm", fg_color=_S.SUCCESS, font=_S.BODY_B,
                      command=self._add_record, height=36).pack(side="left", padx=(0, 6), expand=True, fill="x")
        ctk.CTkButton(btn_frame, text="✏ Sửa", fg_color=_S.PRIMARY, font=_S.BODY_B,
                      command=self._update_record, height=36).pack(side="left", padx=6, expand=True, fill="x")

        btn_frame2 = ctk.CTkFrame(left, fg_color="transparent")
        btn_frame2.pack(fill="x", padx=20, pady=5)
        ctk.CTkButton(btn_frame2, text="💰 Nạp tiền", fg_color=_S.WARNING, font=_S.BODY_B,
                      text_color="white", command=self._topup_balance, height=36
                      ).pack(side="left", padx=(0, 6), expand=True, fill="x")
        ctk.CTkButton(btn_frame2, text="🔄 Làm mới form", fg_color=_S.SURFACE, font=_S.BODY,
                      text_color=_S.TEXT2, command=self._clear_form, height=36
                      ).pack(side="left", padx=(6, 0), expand=True, fill="x")

        # Stats cards & Chart
        stats_frame = ctk.CTkFrame(left, fg_color=_S.SURFACE, corner_radius=10)
        stats_frame.pack(fill="both", expand=True, padx=20, pady=(15, 20))
        
        ctk.CTkLabel(stats_frame, text="📊 Thống kê Hệ thống", font=_S.BODY_B,
                     text_color=_S.PRIMARY).pack(anchor="w", padx=14, pady=(10, 4))

        sf = ctk.CTkFrame(stats_frame, fg_color="transparent")
        sf.pack(fill="x", padx=14, pady=(0, 5))
        sf.grid_columnconfigure(0, weight=1)
        sf.grid_columnconfigure(1, weight=1)

        self.lbl_total_users = ctk.CTkLabel(sf, text="Tổng user: 0", font=_S.BODY,
                                            text_color=_S.TEXT)
        self.lbl_total_users.grid(row=0, column=0, sticky="w")
        self.lbl_total_revenue = ctk.CTkLabel(sf, text="Tổng tiền hệ thống: 0đ", font=_S.BODY,
                                              text_color=_S.TEXT)
        self.lbl_total_revenue.grid(row=0, column=1, sticky="w")
        
        # Chart container
        self.chart_container = ctk.CTkFrame(stats_frame, fg_color="transparent")
        self.chart_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.fig = Figure(figsize=(4, 2.5), dpi=100, facecolor=_S.SURFACE)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_container)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    # ── Right Panel: Treeview + Mã hóa ───────────────────────────────────────
    def _build_right_panel(self):
        right = ctk.CTkFrame(self, fg_color=_S.CARD, corner_radius=14)
        right.grid(row=0, column=1, padx=(7, 14), pady=14, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(right, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        ctk.CTkLabel(hdr, text="📋  Danh Sách Tài Khoản", font=_S.SUBTITLE,
                     text_color=_S.PRIMARY).pack(side="left")
        ctk.CTkButton(hdr, text="⟳ Làm mới", width=100, fg_color=_S.PRIMARY,
                      command=self._load_data).pack(side="right")
        ctk.CTkButton(hdr, text="🗑 Xóa SV đã chọn", width=120, fg_color=_S.DANGER,
                      command=self._delete_selected).pack(side="right", padx=(0, 10))

        # Treeview
        tf = ctk.CTkFrame(right, fg_color="transparent")
        tf.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        tf.grid_columnconfigure(0, weight=1)
        tf.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Mgr.Treeview", rowheight=28, font=("Helvetica", 11),
                        background="#FFFFFF", fieldbackground="#FFFFFF",
                        foreground="#1F2937")
        style.configure("Mgr.Treeview.Heading", font=("Helvetica", 11, "bold"),
                        background="#EEF2F7", foreground="#3B5998")
        style.map("Mgr.Treeview",
                  background=[("selected", "#3B82F6")],
                  foreground=[("selected", "white")])

        cols = ("MaSV", "HoTen", "BienSo", "Lop", "Khoa", "SoDu", "TinhTrang")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings",
                                 style="Mgr.Treeview", height=22, selectmode="extended")

        headings = {"MaSV": "MSSV", "HoTen": "Họ Tên", "BienSo": "Biển Số",
                    "Lop": "Lớp", "Khoa": "Khoa", "SoDu": "Số Dư", "TinhTrang": "Trạng Thái"}
        widths = [90, 160, 110, 80, 130, 100, 90]
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, anchor="center", width=w, stretch=False)

        sy = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        sx = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Barcode generation tools
        gen_tools = ctk.CTkFrame(right, fg_color=_S.SURFACE, corner_radius=10)
        gen_tools.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
        
        # Checkboxes
        chk_frame = ctk.CTkFrame(gen_tools, fg_color="transparent")
        chk_frame.pack(side="left", padx=14, pady=10)
        self.chk_barcode_var = ctk.BooleanVar(value=True)
        self.chk_qr_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(chk_frame, text="Tạo Barcode", variable=self.chk_barcode_var,
                        font=_S.BODY).pack(anchor="w", pady=(0, 5))
        ctk.CTkCheckBox(chk_frame, text="Tạo QR", variable=self.chk_qr_var,
                        font=_S.BODY).pack(anchor="w")
                        
        # Buttons
        btn_tools = ctk.CTkFrame(gen_tools, fg_color="transparent")
        btn_tools.pack(side="right", padx=14, pady=10)
        
        ctk.CTkButton(btn_tools, text="☑ Chọn tất cả", fg_color=_S.PRIMARY, font=_S.BODY,
                      command=self._select_all_tree, width=120, height=42
                      ).pack(side="left", padx=(0, 10))
        
        ctk.CTkButton(
            btn_tools, text="🎲 TẠO MÃ CHO SV ĐÃ CHỌN",
            fg_color=_S.PURPLE, hover_color="#6D28D9", font=_S.BODY_B,
            height=42, command=self._generate_selected_codes
        ).pack(side="left")

    # ── Data operations ───────────────────────────────────────────────────────
    def _load_data(self):
        """Tải dữ liệu từ DB vào Treeview và vẽ biểu đồ (background thread)."""
        def _task():
            try:
                with _connect() as conn:
                    rows = conn.execute("""
                        SELECT sv.MaSV, sv.HoTen, x.BienSo, sv.Lop, sv.Khoa,
                               COALESCE(rfid.SoDu, 0) AS SoDu,
                               COALESCE(rfid.TinhTrang, 'Chưa có thẻ') AS TinhTrang
                        FROM SinhVien sv
                        LEFT JOIN Xe x ON sv.MaSV = x.MaSV
                        LEFT JOIN TheRFID rfid ON sv.MaSV = rfid.MaSV
                        ORDER BY sv.MaSV
                    """).fetchall()

                    total_users = conn.execute("SELECT COUNT(*) FROM SinhVien").fetchone()[0]
                    # Tổng doanh thu là tổng tiền tất cả SV đang có
                    total_rev = conn.execute("SELECT COALESCE(SUM(SoDu), 0) FROM TheRFID").fetchone()[0]

                    # Load data for chart (7 days)
                    history_data = conn.execute("""
                        SELECT date(ThoiGianVao) as dt, 'Vao' as type FROM LichSuVaoRa WHERE ThoiGianVao IS NOT NULL
                        UNION ALL
                        SELECT date(ThoiGianRa) as dt, 'Ra' as type FROM LichSuVaoRa WHERE ThoiGianRa IS NOT NULL
                    """).fetchall()

                self.after(0, lambda: self._update_tree(rows, total_users, total_rev))
                self.after(0, lambda: self._update_chart(history_data))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror("Lỗi", f"Không thể tải dữ liệu: {err_msg}"))

        threading.Thread(target=_task, daemon=True).start()

    def _update_tree(self, rows, total_users, total_rev):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in rows:
            self.tree.insert("", "end", values=(
                r["MaSV"], r["HoTen"], r["BienSo"] or "",
                r["Lop"], r["Khoa"],
                f"{int(r['SoDu']):,}đ",
                r["TinhTrang"]
            ))
        self.lbl_total_users.configure(text=f"Tổng user: {total_users}")
        self.lbl_total_revenue.configure(text=f"Tổng tiền hệ thống: {int(total_rev):,}đ")

    def _update_chart(self, history_data):
        self.ax.clear()
        
        # Prepare last 7 days
        today = datetime.now().date()
        dates = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
        date_strs = [d.strftime("%Y-%m-%d") for d in dates]
        labels = [d.strftime("%d/%m") for d in dates]
        
        counts_in = {d: 0 for d in date_strs}
        counts_out = {d: 0 for d in date_strs}
        
        for row in history_data:
            dt = row["dt"]
            t = row["type"]
            if dt in counts_in:
                if t == "Vao": counts_in[dt] += 1
                else: counts_out[dt] += 1
                
        y_in = [counts_in[d] for d in date_strs]
        y_out = [counts_out[d] for d in date_strs]
        
        x = range(len(labels))
        width = 0.35
        
        self.ax.bar([i - width/2 for i in x], y_in, width, label='Vào', color=_S.PRIMARY)
        self.ax.bar([i + width/2 for i in x], y_out, width, label='Ra', color=_S.WARNING)
        
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
        self.ax.tick_params(axis='y', labelsize=8)
        self.ax.legend(fontsize=8, loc='upper left')
        
        # Thêm lưới
        self.ax.yaxis.grid(True, linestyle='--', alpha=0.7)
        self.ax.set_axisbelow(True)
        
        self.fig.tight_layout(pad=1.0)
        self.fig.patch.set_facecolor(_S.SURFACE)
        self.ax.set_facecolor(_S.SURFACE)
        self.canvas.draw()

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[-1])["values"]  # Lấy item được focus gần nhất
        self._clear_form()
        # vals: MaSV, HoTen, BienSo, Lop, Khoa, SoDu, TinhTrang
        mapping = {
            "MaSV": str(vals[0]),
            "HoTen": str(vals[1]),
            "BienSo": str(vals[2]),
            "Lop": str(vals[3]),
            "Khoa": str(vals[4]),
            "SoDu": str(vals[5]).replace("đ", "").replace(",", "").strip(),
        }
        for key, value in mapping.items():
            if key in self.entries:
                self.entries[key].insert(0, value)
                
        # Update combobox
        state = str(vals[6])
        if state in ["Hoạt động", "Khóa", "Chưa có thẻ"]:
            self.cmb_state.set(state)

    def _clear_form(self):
        for ent in self.entries.values():
            ent.delete(0, "end")
        self.cmb_state.set("Hoạt động")

    def _get_form_data(self) -> dict:
        d = {k: v.get().strip() for k, v in self.entries.items()}
        d["TinhTrang"] = self.cmb_state.get()
        return d

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def _add_record(self):
        d = self._get_form_data()
        if not d["MaSV"] or not d["HoTen"]:
            messagebox.showwarning("Thiếu dữ liệu", "MSSV và Họ tên không được để trống!")
            return

        def _task():
            try:
                with _connect() as conn:
                    # Insert SinhVien
                    conn.execute(
                        "INSERT INTO SinhVien (MaSV, HoTen, Khoa, Lop) VALUES (?, ?, ?, ?)",
                        (d["MaSV"], d["HoTen"], d["Khoa"], d["Lop"])
                    )
                    # Insert Xe nếu có biển số
                    if d["BienSo"]:
                        conn.execute(
                            "INSERT INTO Xe (BienSo, MaSV, LoaiXe, MauSac, TinhTrang) VALUES (?, ?, ?, ?, ?)",
                            (d["BienSo"], d["MaSV"], "", "", "Không Khóa")
                        )
                    # Insert TheRFID
                    so_du = int(d["SoDu"]) if d["SoDu"].isdigit() else 0
                    ma_rfid = f"RFID_UED_{d['MaSV'].replace('SV', '')}"
                    tt = d["TinhTrang"] if d["TinhTrang"] in ["Hoạt động", "Khóa"] else "Hoạt động"
                    conn.execute(
                        "INSERT INTO TheRFID (MaRFID, MaSV, SoDu, TinhTrang) VALUES (?, ?, ?, ?)",
                        (ma_rfid, d["MaSV"], so_du, tt)
                    )
                    conn.commit()

                self.after(0, lambda: (
                    messagebox.showinfo("Thành công", f"Đã thêm sinh viên {d['MaSV']}!"),
                    self._load_data()
                ))
            except sqlite3.IntegrityError as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror(
                    "Lỗi ràng buộc", f"Dữ liệu bị trùng hoặc vi phạm khóa!\n{err_msg}"))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror("Lỗi", err_msg))

        threading.Thread(target=_task, daemon=True).start()

    def _update_record(self):
        d = self._get_form_data()
        if not d["MaSV"]:
            messagebox.showwarning("Thiếu dữ liệu", "Phải chọn MSSV để sửa!")
            return

        def _task():
            try:
                with _connect() as conn:
                    conn.execute(
                        "UPDATE SinhVien SET HoTen=?, Khoa=?, Lop=? WHERE MaSV=?",
                        (d["HoTen"], d["Khoa"], d["Lop"], d["MaSV"])
                    )
                    
                    if d["BienSo"]:
                        # Cập nhật biển số
                        xe_exists = conn.execute("SELECT 1 FROM Xe WHERE MaSV=?", (d["MaSV"],)).fetchone()
                        if xe_exists:
                            conn.execute("UPDATE Xe SET BienSo=? WHERE MaSV=?", (d["BienSo"], d["MaSV"]))
                        else:
                            conn.execute(
                                "INSERT INTO Xe (BienSo, MaSV, LoaiXe, MauSac, TinhTrang) VALUES (?, ?, ?, ?, ?)",
                                (d["BienSo"], d["MaSV"], "", "", "Không Khóa")
                            )
                            
                    # Cập nhật RFID status nếu không phải "Chưa có thẻ"
                    if d["TinhTrang"] in ["Hoạt động", "Khóa"]:
                        rfid_exists = conn.execute("SELECT 1 FROM TheRFID WHERE MaSV=?", (d["MaSV"],)).fetchone()
                        if rfid_exists:
                            conn.execute("UPDATE TheRFID SET TinhTrang=? WHERE MaSV=?", (d["TinhTrang"], d["MaSV"]))
                        else:
                            ma_rfid = f"RFID_UED_{d['MaSV'].replace('SV', '')}"
                            conn.execute(
                                "INSERT INTO TheRFID (MaRFID, MaSV, SoDu, TinhTrang) VALUES (?, ?, 0, ?)",
                                (ma_rfid, d["MaSV"], d["TinhTrang"])
                            )

                    conn.commit()
                self.after(0, lambda: (
                    messagebox.showinfo("Thành công", f"Đã cập nhật {d['MaSV']}!"),
                    self._load_data()
                ))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror("Lỗi", err_msg))

        threading.Thread(target=_task, daemon=True).start()

    def _delete_selected(self):
        """Xóa các sinh viên đang được chọn trong Treeview."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn ít nhất 1 sinh viên trong danh sách để xóa.")
            return
            
        sv_list = [self.tree.item(item)["values"][0] for item in sel]
        if not messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc chắn muốn xóa {len(sv_list)} sinh viên đã chọn cùng toàn bộ dữ liệu liên quan?"):
            return

        def _task():
            try:
                with _connect() as conn:
                    for ma_sv in sv_list:
                        conn.execute("""
                            DELETE FROM LichSuVaoRa WHERE MaRFID IN
                            (SELECT MaRFID FROM TheRFID WHERE MaSV = ?)
                        """, (ma_sv,))
                        conn.execute("DELETE FROM TheRFID WHERE MaSV = ?", (ma_sv,))
                        conn.execute("DELETE FROM Xe WHERE MaSV = ?", (ma_sv,))
                        conn.execute("DELETE FROM SinhVien WHERE MaSV = ?", (ma_sv,))
                    conn.commit()
                self.after(0, lambda: (
                    messagebox.showinfo("Thành công", f"Đã xóa {len(sv_list)} sinh viên!"),
                    self._clear_form(),
                    self._load_data()
                ))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror("Lỗi", err_msg))

        threading.Thread(target=_task, daemon=True).start()

    # ── Nạp tiền ──────────────────────────────────────────────────────────────
    def _topup_balance(self):
        d = self._get_form_data()
        if not d["MaSV"]:
            messagebox.showwarning("Thiếu dữ liệu", "Chọn sinh viên trên bảng trước!")
            return

        popup = ctk.CTkToplevel(self)
        popup.title(f"💰 Quản lý Số dư — {d['MaSV']}")
        popup.geometry("380x250")
        popup.resizable(False, False)

        self.after(100, popup.grab_set)

        ctk.CTkLabel(popup, text=f"Tài khoản: {d['HoTen']} ({d['MaSV']})\nSố dư hiện tại: {d['SoDu']}đ",
                     font=_S.BODY_B, wraplength=350, justify="center").pack(pady=(20, 15))

        ent_amount = ctk.CTkEntry(popup, placeholder_text="Nhập số tiền (VNĐ)", height=36,
                                  fg_color=_S.SURFACE)
        ent_amount.pack(fill="x", padx=30, pady=5)
        ent_amount.focus()

        def _do_update(is_add=True):
            amount_str = ent_amount.get().strip().replace(",", "").replace(".", "")
            if not amount_str.isdigit() or int(amount_str) <= 0:
                messagebox.showwarning("Lỗi", "Vui lòng nhập số tiền hợp lệ!")
                return
            amount = int(amount_str)
            if not is_add:
                amount = -amount
            ma_sv = d["MaSV"]

            def _task():
                try:
                    with _connect() as conn:
                        conn.execute(
                            "UPDATE TheRFID SET SoDu = SoDu + ? WHERE MaSV = ?",
                            (amount, ma_sv)
                        )
                        conn.commit()
                    action_str = "Cộng" if is_add else "Trừ"
                    self.after(0, lambda: (
                        messagebox.showinfo("Thành công", f"Đã {action_str} {abs(amount):,}đ cho {ma_sv}!"),
                        popup.destroy(),
                        self._load_data()
                    ))
                except Exception as e:
                    err_msg = str(e)
                    self.after(0, lambda: messagebox.showerror("Lỗi", err_msg))

            threading.Thread(target=_task, daemon=True).start()

        btn_row = ctk.CTkFrame(popup, fg_color="transparent")
        btn_row.pack(fill="x", padx=30, pady=(15, 20))
        ctk.CTkButton(btn_row, text="➕ Cộng tiền", fg_color=_S.SUCCESS, font=_S.BODY_B,
                      command=lambda: _do_update(True), height=38).pack(side="left", expand=True, padx=(0, 5))
        ctk.CTkButton(btn_row, text="➖ Trừ tiền", fg_color=_S.WARNING, text_color="white", font=_S.BODY_B,
                      command=lambda: _do_update(False), height=38).pack(side="left", expand=True, padx=(5, 0))

    # ── Sinh mã hàng loạt ────────────────────────────────────────────────────
    def _select_all_tree(self):
        self.tree.selection_set(self.tree.get_children())
        
    def _generate_selected_codes(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn ít nhất 1 sinh viên trong danh sách để tạo mã.")
            return
            
        sv_list = [self.tree.item(item)["values"][0] for item in sel]
        
        def _task():
            try:
                from createbarcode.generator import generate_qr, generate_barcode

                with _connect() as conn:
                    placeholders = ",".join("?" for _ in sv_list)
                    rows = conn.execute(f"""
                        SELECT sv.MaSV, sv.HoTen, sv.Lop, sv.Khoa, x.BienSo
                        FROM SinhVien sv
                        LEFT JOIN Xe x ON sv.MaSV = x.MaSV
                        WHERE sv.MaSV IN ({placeholders})
                    """, sv_list).fetchall()

                qr_count = 0
                bc_count = 0
                for r in rows:
                    gen_data = {
                        "MSSV": r["MaSV"],
                        "BienSo": r["BienSo"] or "",
                        "HoTen": r["HoTen"],
                        "Lop": r["Lop"],
                        "Khoa": r["Khoa"],
                    }
                    if self.chk_qr_var.get():
                        if generate_qr(gen_data):
                            qr_count += 1
                    if self.chk_barcode_var.get():
                        if generate_barcode(gen_data):
                            bc_count += 1

                self.after(0, lambda: messagebox.showinfo(
                    "Hoàn tất",
                    f"Đã tạo thành công:\n"
                    f"  • {qr_count} mã QR\n"
                    f"  • {bc_count} Barcode\n\n"
                    f"Lưu tại: {BARCODES_DIR}"
                ))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror("Lỗi sinh mã", err_msg))

        threading.Thread(target=_task, daemon=True).start()


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = GeneratorManagerApp()
    app.mainloop()
