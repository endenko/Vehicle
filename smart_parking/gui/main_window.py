"""
Main GUI Window - SmartParking Valkyrie
Giao diện chính với Camera Scanner (trái) + Parked Vehicles List (phải)
"""
import tkinter as tk
from tkinter import ttk
import cv2
from PIL import Image, ImageTk
import threading
import time
from typing import Optional, Callable

from smart_parking.camera_scanner import CameraScanner
from smart_parking.database import db_manager
from smart_parking.fuzzy_auth import authenticate_with_ocr
from smart_parking.gui.dashboard import StatisticsDashboard
from smart_parking.config import (
    GUI_TITLE, GUI_WIDTH, GUI_HEIGHT, GUI_BG_COLOR, 
    CAMERA_INDEX, CAMERA_FRAME_WIDTH, CAMERA_FRAME_HEIGHT
)

class SmartParkingMainWindow:
    """Cửa sổ chính của ứng dụng"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(GUI_TITLE)
        self.root.geometry(f"{GUI_WIDTH}x{GUI_HEIGHT}")
        self.root.configure(bg=GUI_BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # State
        self.running = True
        self.scanner: Optional[CameraScanner] = None
        self.last_student_id = None
        self.parked_vehicles = []
        
        # Biến Tkinter
        self.camera_update_thread = None
        self.parked_update_thread = None
        self.qr_detected_var = tk.StringVar(value="-")
        self.last_student_var = tk.StringVar(value="-")
        
        # Khởi tạo
        self._init_database()
        self._init_camera()
        self._build_ui()
        self._start_update_loops()
    
    def _init_database(self):
        """Khởi tạo database"""
        if not db_manager.connect():
            print("[✗] Không thể kết nối database!")
    
    def _init_camera(self):
        """Khởi tạo camera"""
        try:
            self.scanner = CameraScanner(camera_index=CAMERA_INDEX)
            print("[✓] Camera khởi tạo thành công")
        except Exception as e:
            print(f"[✗] Lỗi camera: {e}")
            self.scanner = None
    
    def _build_ui(self):
        """Xây dựng UI"""
        # 1. DASHBOARD (Full-width header)
        self.dashboard = StatisticsDashboard(
            self.root,
            stats_callback=db_manager.get_statistics,
            bg_color="#34495e"
        )
        self.dashboard.start_auto_refresh(interval=3.0)
        
        # 2. MAIN CONTENT AREA
        content_frame = tk.Frame(self.root, bg=GUI_BG_COLOR)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        content_frame.columnconfigure(0, weight=2)  # Camera area
        content_frame.columnconfigure(1, weight=1)  # Right panel
        content_frame.rowconfigure(0, weight=1)
        
        # --- LEFT: CAMERA ---
        camera_frame = ttk.LabelFrame(content_frame, text="📹 Camera Quét Mã Sinh Viên", padding=5)
        camera_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)
        camera_frame.columnconfigure(0, weight=1)
        camera_frame.rowconfigure(0, weight=1)
        
        self.video_label = tk.Label(camera_frame, bg="black", width=640, height=480)
        self.video_label.grid(row=0, column=0, sticky="nsew")
        
        # Info dưới camera
        info_frame = tk.Frame(camera_frame, bg="#2c3e50")
        info_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        tk.Label(info_frame, text="Mã SV quét được:", font=("Arial", 9), bg="#2c3e50", fg="lightgray").pack(side=tk.LEFT)
        tk.Label(info_frame, textvariable=self.qr_detected_var, font=("Arial", 11, "bold"), bg="#2c3e50", fg="lime").pack(side=tk.LEFT, padx=(5, 0))
        
        # --- RIGHT: PARKED VEHICLES ---
        right_panel = ttk.LabelFrame(content_frame, text="🚗 Xe Đang Đỗ (Click để xem chi tiết)", padding=5)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)
        
        # Scrollable list
        canvas = tk.Canvas(right_panel, bg="#2c3e50", highlightthickness=0)
        scrollbar = ttk.Scrollbar(right_panel, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#2c3e50")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        def on_canvas_configure(e):
            canvas.itemconfig(canvas_window, width=e.width)
        
        canvas.bind('<Configure>', on_canvas_configure)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        self.parked_vehicles_frame = scrollable_frame
    
    def _start_update_loops(self):
        """Bắt đầu các luồng update"""
        self.camera_update_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self.camera_update_thread.start()
        
        self.parked_update_thread = threading.Thread(target=self._parked_vehicles_loop, daemon=True)
        self.parked_update_thread.start()
    
    def _camera_loop(self):
        """Luồng update camera"""
        while self.running:
            if self.scanner is None:
                time.sleep(0.1)
                continue
            
            try:
                ret, frame = self.scanner.read_frame()
                if not ret:
                    continue
                
                # Detect QR/Barcode
                result = self.scanner.detect_any_code(frame)
                
                if result:
                    code, code_type = result
                    self.last_student_id = code
                    self.root.after(0, self.qr_detected_var.set, f"{code} ({code_type})")
                    
                    # Nếu là mã sinh viên, xác thực
                    if code.startswith("SV"):
                        self._handle_student_scan(code)
                
                # Display frame
                display_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(display_frame)
                img = img.resize((640, 480), Image.Resampling.LANCZOS)
                imgtk = ImageTk.PhotoImage(image=img)
                
                self.root.after(0, self._update_video_label, imgtk)
                
                time.sleep(0.033)  # ~30 FPS
            
            except Exception as e:
                print(f"[✗] Lỗi camera loop: {e}")
                time.sleep(1)
    
    def _update_video_label(self, imgtk):
        """Update video label"""
        self.video_label.imgtk = imgtk
        self.video_label.configure(image=imgtk)
    
    def _handle_student_scan(self, ma_sv: str):
        """Xử lý khi quét mã sinh viên"""
        student = db_manager.get_student_by_id(ma_sv)
        if student:
            self.last_student_var.set(f"{student['ho_ten']} ({ma_sv})")
    
    def _parked_vehicles_loop(self):
        """Luồng update danh sách xe đang đỗ"""
        while self.running:
            try:
                parked = db_manager.get_parked_vehicles()
                self.root.after(0, self._update_parked_list, parked)
                time.sleep(5)  # Update mỗi 5 giây
            except Exception as e:
                print(f"[✗] Lỗi parked loop: {e}")
                time.sleep(5)
    
    def _update_parked_list(self, parked: list):
        """Update danh sách xe đang đỗ"""
        # Xóa items cũ
        for widget in self.parked_vehicles_frame.winfo_children():
            widget.destroy()
        
        if not parked:
            tk.Label(
                self.parked_vehicles_frame,
                text="⚪ Không có xe đang đỗ",
                font=("Arial", 10),
                bg="#2c3e50",
                fg="lightgray"
            ).pack(padx=5, pady=10)
            return
        
        for vehicle in parked:
            self._create_vehicle_item(vehicle)
    
    def _create_vehicle_item(self, vehicle: dict):
        """Tạo item cho một chiếc xe"""
        item_frame = tk.Frame(self.parked_vehicles_frame, bg="#34495e", relief="raised", bd=1)
        item_frame.pack(fill=tk.X, padx=5, pady=3)
        
        # Plate
        plate_label = tk.Label(
            item_frame,
            text=vehicle['bien_so'],
            font=("Arial", 12, "bold"),
            bg="#34495e",
            fg="lime"
        )
        plate_label.pack(anchor="w", padx=10, pady=(5, 0))
        
        # Student info
        student_info = f"{vehicle['ho_ten']} - {vehicle['lop']}"
        student_label = tk.Label(
            item_frame,
            text=student_info,
            font=("Arial", 9),
            bg="#34495e",
            fg="lightgray"
        )
        student_label.pack(anchor="w", padx=10)
        
        # Time
        time_label = tk.Label(
            item_frame,
            text=f"Vào: {vehicle['gio_vao'].strftime('%H:%M:%S')}",
            font=("Arial", 8),
            bg="#34495e",
            fg="gray"
        )
        time_label.pack(anchor="w", padx=10, pady=(0, 5))
    
    def on_close(self):
        """Đóng ứng dụng"""
        self.running = False
        self.dashboard.stop_auto_refresh()
        
        if self.scanner:
            self.scanner.release()
        
        db_manager.disconnect()
        
        if self.camera_update_thread:
            self.camera_update_thread.join(timeout=2)
        if self.parked_update_thread:
            self.parked_update_thread.join(timeout=2)
        
        self.root.destroy()

def run_main_gui():
    """Chạy ứng dụng GUI chính"""
    root = tk.Tk()
    app = SmartParkingMainWindow(root)
    root.mainloop()

if __name__ == "__main__":
    run_main_gui()
