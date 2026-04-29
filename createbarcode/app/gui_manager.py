import os
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR.parent / "database.db"

class GeneratorManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Quản Lý Dữ Liệu & Sinh Mã")
        self.geometry("1100x700")
        
        # Grid config
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        # LEFT PANEL - Treeview
        left_frame = ctk.CTkFrame(self, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)
        
        lbl_title = ctk.CTkLabel(left_frame, text="Danh Sách Sinh Viên", font=("Helvetica", 20, "bold"))
        lbl_title.grid(row=0, column=0, sticky="w", pady=(0, 10))
        
        # Style for Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=25, font=("Helvetica", 11))
        style.configure("Treeview.Heading", font=("Helvetica", 11, "bold"))
        
        cols = ("MaSV", "HoTen", "Khoa", "Lop", "SDT", "MaRFID")
        self.tree = ttk.Treeview(left_frame, columns=cols, show="headings", height=20)
        for c in cols:
            self.tree.heading(c, text=c)
        
        self.tree.column("MaSV", width=100)
        self.tree.column("HoTen", width=180)
        self.tree.column("Khoa", width=120)
        self.tree.column("Lop", width=80)
        self.tree.column("SDT", width=120)
        self.tree.column("MaRFID", width=120)
        
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        
        sy = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        sy.grid(row=1, column=1, sticky="ns")
        
        # RIGHT PANEL - Forms
        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(right_frame, text="Thông Tin Sinh Viên", font=("Helvetica", 18, "bold")).pack(pady=10)
        
        self.entries = {}
        fields = [("Mã SV:", "MaSV"), ("Họ Tên:", "HoTen"), ("Khoa:", "Khoa"), 
                  ("Lớp:", "Lop"), ("SĐT:", "SDT"), ("Mã RFID:", "MaRFID")]
                  
        for label, key in fields:
            f = ctk.CTkFrame(right_frame, fg_color="transparent")
            f.pack(fill="x", padx=15, pady=5)
            ctk.CTkLabel(f, text=label, width=80, anchor="w").pack(side="left")
            ent = ctk.CTkEntry(f)
            ent.pack(side="left", fill="x", expand=True)
            self.entries[key] = ent
            
        # Buttons
        btn_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=20)
        
        ctk.CTkButton(btn_frame, text="Thêm", command=self.add_record, fg_color="#10B981").pack(side="left", padx=5, expand=True)
        ctk.CTkButton(btn_frame, text="Sửa", command=self.update_record, fg_color="#3B82F6").pack(side="left", padx=5, expand=True)
        ctk.CTkButton(btn_frame, text="Xóa", command=self.delete_record, fg_color="#EF4444").pack(side="left", padx=5, expand=True)
        
        ctk.CTkButton(right_frame, text="Làm Mới Form", command=self.clear_form, fg_color="gray").pack(pady=5)
        
        # Generator Button
        gen_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        gen_frame.pack(side="bottom", fill="x", padx=15, pady=20)
        ctk.CTkButton(gen_frame, text="TẠO MÃ BROWSE & QR CHO TOÀN BỘ SV", 
                     command=self.generate_codes, fg_color="#8B5CF6", font=("Helvetica", 13, "bold"), height=40).pack(fill="x")

    def connect_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def load_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        try:
            with self.connect_db() as conn:
                rows = conn.execute("""
                    SELECT sv.MaSV, sv.HoTen, sv.Khoa, sv.Lop, sv.SDT, rfid.MaRFID
                    FROM SinhVien sv
                    LEFT JOIN TheRFID rfid ON sv.MaSV = rfid.MaSV
                """).fetchall()
                for r in rows:
                    self.tree.insert("", "end", values=(
                        r["MaSV"], r["HoTen"], r["Khoa"], r["Lop"], r["SDT"], r["MaRFID"] or ""
                    ))
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể tải dữ liệu: {e}")

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        item = self.tree.item(sel[0])["values"]
        self.clear_form()
        keys = ["MaSV", "HoTen", "Khoa", "Lop", "SDT", "MaRFID"]
        for i, key in enumerate(keys):
            self.entries[key].insert(0, str(item[i]) if item[i] is not None else "")

    def clear_form(self):
        for ent in self.entries.values():
            ent.delete(0, "end")

    def add_record(self):
        data = {k: v.get().strip() for k, v in self.entries.items()}
        if not data["MaSV"] or not data["HoTen"]:
            messagebox.showwarning("Thiếu dữ liệu", "Mã SV và Họ Tên không được để trống!")
            return
            
        try:
            with self.connect_db() as conn:
                conn.execute("""
                    INSERT INTO SinhVien (MaSV, HoTen, Khoa, Lop, SDT)
                    VALUES (?, ?, ?, ?, ?)
                """, (data["MaSV"], data["HoTen"], data["Khoa"], data["Lop"], data["SDT"]))
                
                if data["MaRFID"]:
                    conn.execute("""
                        INSERT INTO TheRFID (MaRFID, MaSV, SoDu, TinhTrang)
                        VALUES (?, ?, 0, 'Hoạt động')
                    """, (data["MaRFID"], data["MaSV"]))
            messagebox.showinfo("Thành công", "Đã thêm dữ liệu!")
            self.load_data()
        except sqlite3.IntegrityError as e:
            messagebox.showerror("Lỗi Logic / Ràng buộc (Warning)", f"Dữ liệu bị trùng lặp hoặc vi phạm khóa ngoại!\nĐã Rollback.\nChi tiết: {e}")
        except Exception as e:
            messagebox.showerror("Lỗi Rollback", f"Đã rollback do lỗi: {e}")

    def update_record(self):
        data = {k: v.get().strip() for k, v in self.entries.items()}
        if not data["MaSV"]:
            messagebox.showwarning("Thiếu dữ liệu", "Phải chọn Mã SV để sửa!")
            return
            
        try:
            with self.connect_db() as conn:
                conn.execute("""
                    UPDATE SinhVien 
                    SET HoTen=?, Khoa=?, Lop=?, SDT=?
                    WHERE MaSV=?
                """, (data["HoTen"], data["Khoa"], data["Lop"], data["SDT"], data["MaSV"]))
                
                if data["MaRFID"]:
                    # Xóa cũ thay mới
                    conn.execute("DELETE FROM TheRFID WHERE MaSV=?", (data["MaSV"],))
                    conn.execute("""
                        INSERT INTO TheRFID (MaRFID, MaSV, SoDu, TinhTrang)
                        VALUES (?, ?, 0, 'Hoạt động')
                    """, (data["MaRFID"], data["MaSV"]))
            messagebox.showinfo("Thành công", "Đã cập nhật!")
            self.load_data()
        except sqlite3.IntegrityError as e:
            messagebox.showerror("Lỗi Ràng Buộc", f"Không thể cập nhật do vi phạm ràng buộc!\nĐã Rollback.\nChi tiết: {e}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Rollback lỗi: {e}")

    def delete_record(self):
        masv = self.entries["MaSV"].get().strip()
        if not masv: return
        
        if not messagebox.askyesno("Xác nhận", f"Xóa toàn bộ dữ liệu của SV: {masv}?"):
            return
            
        try:
            with self.connect_db() as conn:
                conn.execute("DELETE FROM TheRFID WHERE MaSV=?", (masv,))
                # Nếu muốn chuẩn chỉ, xóa cả Xe và Lịch sử nếu có, nhưng SQLite CASCADE làm việc này nếu set PRAGMA foreign_keys=ON
                # (Với điều kiện ON DELETE CASCADE trong schema, ở đây schema không có CASCADE nên phải xóa thủ công hoặc báo lỗi)
                conn.execute("DELETE FROM SinhVien WHERE MaSV=?", (masv,))
            messagebox.showinfo("Thành công", "Đã xóa!")
            self.clear_form()
            self.load_data()
        except sqlite3.IntegrityError as e:
            messagebox.showerror("Lỗi Ràng Buộc (FK)", f"Không thể xóa SV này vì vẫn còn Xe hoặc Lịch Sử tồn tại trong bãi!\nVui lòng xóa Xe trước.\nĐã Rollback.\nChi tiết: {e}")
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

    def generate_codes(self):
        try:
            import app.qr_generator as qg
            from app.database import _build_product_code, _build_ref_code
            
            # Tạo thư mục đích theo yêu cầu
            barcode_dir = qg.ROOT_DIR / "barcodes"
            barcode_dir.mkdir(parents=True, exist_ok=True)
            
            generated_qr = []
            generated_barcode = []
            
            with self.connect_db() as conn:
                rows = conn.execute("""
                    SELECT sv.MaSV, sv.HoTen, sv.Khoa, sv.Lop, sv.SDT, rfid.MaRFID
                    FROM SinhVien sv
                    LEFT JOIN TheRFID rfid ON sv.MaSV = rfid.MaSV
                """).fetchall()
                
            for row in rows:
                ma_sv = row["MaSV"]
                # Giả lập payload student giống hệt cấu trúc cũ của TestCamera
                student = {
                    "student_id": ma_sv,
                    "full_name": row["HoTen"],
                    "class_name": row["Lop"],
                    "dob": "01/01/2000",
                    "major": row["Khoa"],
                    "email": f"{ma_sv.lower()}@ued.udn.vn",
                    "phone": row["SDT"],
                    "ref_code": row["MaRFID"] or _build_ref_code(ma_sv),
                    "product_code": _build_product_code(ma_sv),
                }
                
                qr_path = qg.generate_qr_for_student(student, output_dir=barcode_dir)
                generated_qr.append(str(qr_path))
                
                barcode_path = qg.generate_barcode_for_student(student, output_dir=barcode_dir)
                generated_barcode.append(str(barcode_path))
                
            messagebox.showinfo("Hoàn tất", 
                f"Đã tạo thành công:\n- {len(generated_qr)} mã QR\n- {len(generated_barcode)} Barcode\n\nLưu tại: {barcode_dir}")
        except Exception as e:
            messagebox.showerror("Lỗi sinh mã", f"Có lỗi xảy ra: {e}")

if __name__ == "__main__":
    app = GeneratorManagerApp()
    app.mainloop()
