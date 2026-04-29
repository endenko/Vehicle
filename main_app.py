import cv2
import os
import time
import threading
import base64
import requests
import importlib
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from google.cloud import vision
from fuzzy_auth import authenticate_vehicle

# Thiết lập khóa an ninh Google Cloud Vision
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_PATH = os.path.join(CURRENT_DIR, "key.json")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH

try:
    vision_client = vision.ImageAnnotatorClient()
except Exception as e:
    print(f"[LỖI CỤC BỘ] Lỗi khởi tạo Cloud Vision: {e}")

class SmartParkingValkyrie:
    def __init__(self, root):
        self.root = root
        self.root.title("Cục Cảnh sát Valkyrie - Trạm Kiểm soát Bãi Đỗ Xe Thông Minh")
        self.root.geometry("1300x800")
        self.root.configure(bg="#2c3e50")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.running = True
        self.current_ma_sv = None
        self.cap = cv2.VideoCapture(0) # Camera Laptop quét QR

        try:
            self.zxingcpp = importlib.import_module("zxingcpp")
        except ModuleNotFoundError:
            self.zxingcpp = None
            print("[CẢNH BÁO] Không có zxingcpp. Vui lòng cài đặt: pip install zxing-cpp")

        self.setup_ui()
        self.update_camera()

    def setup_ui(self):
        # 1. STATISTICS DASHBOARD (FULL-WIDTH HEADER)
        self.header_frame = tk.Frame(self.root, bg="#34495e", height=90)
        self.header_frame.pack(side=tk.TOP, fill=tk.X)
        self.header_frame.pack_propagate(False)

        tk.Label(self.header_frame, text="TỔNG TRẠM GIÁM SÁT AN NINH VALKYRIE", font=("Arial", 18, "bold"), fg="#2ecc71", bg="#34495e").pack(pady=(10, 5))
        self.lbl_stats = tk.Label(self.header_frame, text="SẴN SÀNG NHẬN DIỆN MỤC TIÊU", font=("Arial", 12), fg="white", bg="#34495e")
        self.lbl_stats.pack()

        # 2. KHU VỰC QUÉT MÃ QR LAPTOP (TRÁI)
        self.left_panel = ttk.LabelFrame(self.root, text="Camera Trạm Giám Sát (Laptop - Quét Mã SV)")
        self.left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.lbl_video = tk.Label(self.left_panel, bg="black")
        self.lbl_video.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.lbl_qr_result = tk.Label(self.left_panel, text="MÃ SV: ĐANG CHỜ QUÉT...", font=("Arial", 16, "bold"), fg="orange")
        self.lbl_qr_result.pack(pady=10)

        # 3. KHU VỰC ESP32 VÀ THẨM ĐỊNH (PHẢI)
        self.right_panel = tk.Frame(self.root, width=500, bg="#2c3e50")
        self.right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        self.right_panel.pack_propagate(False)

        # Khung giả lập ESP32
        self.esp32_frame = ttk.LabelFrame(self.right_panel, text="Tín hiệu Trinh sát (ESP32-CAM & YOLO)")
        self.esp32_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_esp32_img = tk.Label(self.esp32_frame, text="[CHỜ ẢNH CHỤP TỪ ESP32]", bg="black", fg="white", height=12)
        self.lbl_esp32_img.pack(fill=tk.X, padx=10, pady=10)

        # Nút giả lập (Dành cho Sensei test hệ thống)
        tk.Button(self.esp32_frame, text="Giả lập ESP32 Gửi Ảnh Biển Số", bg="blue", fg="white", font=("Arial", 10, "bold"), 
                  command=self.simulate_esp32_trigger).pack(pady=5)

        # Khung kết quả
        self.auth_frame = ttk.LabelFrame(self.right_panel, text="Phòng Thẩm Định (Cloud Vision + Fuzzy Logic)")
        self.auth_frame.pack(fill=tk.X, pady=5)

        self.lbl_ocr_raw = tk.Label(self.auth_frame, text="Dữ liệu Cloud Vision: ---", font=("Arial", 10), fg="gray")
        self.lbl_ocr_raw.pack(pady=5)

        self.lbl_decision = tk.Label(self.auth_frame, text="TRẠNG THÁI: KHÓA", font=("Arial", 16, "bold"), fg="red")
        self.lbl_decision.pack(pady=10)

        # Nhật ký
        self.log_frame = ttk.LabelFrame(self.right_panel, text="Nhật Ký Hệ Thống")
        self.log_frame.pack(fill=tk.BOTH, expand=True)
        self.listbox_log = tk.Listbox(self.log_frame, bg="#ecf0f1", font=("Arial", 10))
        self.listbox_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def update_camera(self):
        if not self.running: return

        ret, frame = self.cap.read()
        if ret:
            # Liên tục quét QR bằng zxingcpp
            if self.zxingcpp:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                results = self.zxingcpp.read_barcodes(gray)
                if results:
                    code_text = str(results[0].text).strip()
                    # Cập nhật mã SV hiện tại nếu quét thành công
                    if code_text.startswith("SV"):
                        self.current_ma_sv = code_text
                        self.lbl_qr_result.config(text=f"MÃ SV: {self.current_ma_sv}", fg="green")

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb_frame).resize((600, 450), Image.Resampling.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            self.lbl_video.imgtk = imgtk
            self.lbl_video.configure(image=imgtk)

        self.root.after(30, self.update_camera)

    def simulate_esp32_trigger(self):
        """Giả lập việc ESP32 gửi ảnh lên sau khi sensor IR bị cắt"""
        if not self.current_ma_sv:
            self.listbox_log.insert(0, f"[{time.strftime('%H:%M:%S')}] CẢNH BÁO: Xe vào nhưng chưa có mã Sinh Viên!")
            return

        # Trong thực tế, đây là file ảnh nhận từ request của ESP32.
        # Ở đây dùng lệnh cap.read() giả lập làm ảnh ESP32.
        ret, frame = self.cap.read() 
        if ret:
            self.lbl_decision.config(text="ĐANG PHÂN TÍCH...", fg="orange")
            threading.Thread(target=self.process_vision_and_fuzzy, args=(frame,), daemon=True).start()

    def process_vision_and_fuzzy(self, image_frame):
        is_success, buffer = cv2.imencode(".jpg", image_frame)
        if not is_success: return

        try:
            # 1. Gửi lên Cloud Vision
            gcv_image = vision.Image(content=buffer.tobytes())
            response = vision_client.text_detection(image=gcv_image)
            
            raw_text = "KHÔNG ĐỌC ĐƯỢC"
            if response.text_annotations:
                raw_text = response.text_annotations[0].description.strip()
            
            self.root.after(0, self.lbl_ocr_raw.config, {"text": f"Dữ liệu Cloud Vision: {repr(raw_text)}"})

            # 2. Đưa vào phòng thẩm định Fuzzy Logic
            is_valid, msg, matched_plate = authenticate_vehicle(self.current_ma_sv, raw_text)

            # 3. Cập nhật kết quả
            color = "green" if is_valid else "red"
            decision_text = "MỞ CỔNG" if is_valid else "TỪ CHỐI"
            
            self.root.after(0, self.lbl_decision.config, {"text": f"TRẠNG THÁI: {decision_text}\n{msg}", "fg": color})
            self.root.after(0, self.listbox_log.insert, 0, f"[{time.strftime('%H:%M:%S')}] {self.current_ma_sv} - {msg}")
            
        except Exception as e:
            self.root.after(0, self.lbl_decision.config, {"text": "LỖI KẾT NỐI API", "fg": "red"})

    def on_close(self):
        self.running = False
        self.cap.release()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = SmartParkingValkyrie(root)
    root.mainloop()