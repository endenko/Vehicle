import cv2
import os
import time
import threading
import base64
import re
import requests
import importlib
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import pytesseract
from fuzzy_auth import authenticate_vehicle

# Roboflow API cấu hình
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROBOFLOW_API_KEY = "AMrcEXneFYP87Cn5lZP1"
ROBOFLOW_URL = f"https://detect.roboflow.com/vietnam-license-plate-h8t3n/1?api_key={ROBOFLOW_API_KEY}"

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
        self.auth_frame = ttk.LabelFrame(self.right_panel, text="Phòng Thẩm Định (Roboflow + Tesseract + Fuzzy Logic)")
        self.auth_frame.pack(fill=tk.X, pady=5)

        self.lbl_ocr_raw = tk.Label(self.auth_frame, text="Dữ liệu OCR: ---", font=("Arial", 10), fg="gray")
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
            threading.Thread(target=self.process_plate_detection, args=(frame,), daemon=True).start()

    def process_plate_detection(self, image_frame):
        is_success, buffer = cv2.imencode(".jpg", image_frame)
        if not is_success:
            return

        predictions = self.get_roboflow_predictions(image_frame)
        if not predictions:
            self.root.after(0, self.lbl_ocr_raw.config, {"text": "Dữ liệu Roboflow: KHÔNG PHÁT HIỆN BIỂN SỐ"})
            self.root.after(0, self.lbl_decision.config, {"text": "TRẠNG THÁI: KHÔNG THẤY BIỂN SỐ", "fg": "orange"})
            return

        best_pred = max(predictions, key=lambda p: float(p.get('confidence', 0)))
        center_x, center_y = int(best_pred['x']), int(best_pred['y'])
        w, h = int(best_pred['width']), int(best_pred['height'])

        pad_x, pad_y = int(w * 0.15), int(h * 0.08)
        x1 = max(0, int(center_x - w / 2) - pad_x)
        y1 = max(0, int(center_y - h / 2) - pad_y)
        x2 = min(image_frame.shape[1], int(center_x + w / 2) + pad_x)
        y2 = min(image_frame.shape[0], int(center_y + h / 2) + pad_y)

        plate_crop = image_frame[y1:y2, x1:x2]
        raw_plate_text = self.read_plate_text(plate_crop)
        if raw_plate_text:
            clean_text = self.clean_extracted_text(raw_plate_text)
        else:
            clean_text = "UNKNOWN"
            raw_plate_text = ""

        timestamp = time.strftime("%H%M%S")
        evidence_name = f"OCR_Success_{clean_text}_{timestamp}.jpg" if clean_text != "UNKNOWN" else f"UNKNOWN_{timestamp}.jpg"
        save_path = os.path.join(CURRENT_DIR, evidence_name)
        cv2.imwrite(save_path, plate_crop)

        self.root.after(0, self.lbl_ocr_raw.config, {"text": f"Dữ liệu Roboflow/Tesseract: {repr(raw_plate_text)}"})

        is_valid, msg, matched_plate = authenticate_vehicle(self.current_ma_sv, clean_text)
        color = "green" if is_valid else "red"
        decision_text = "MỞ CỔNG" if is_valid else "TỪ CHỐI"

        self.root.after(0, self.lbl_decision.config, {"text": f"TRẠNG THÁI: {decision_text}\n{msg}", "fg": color})
        self.root.after(0, self.listbox_log.insert, 0, f"[{time.strftime('%H:%M:%S')}] {self.current_ma_sv} - {msg} - Plate: {clean_text}")

        cropped_rgb = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2RGB)
        crop_img_main = Image.fromarray(cropped_rgb).resize((300, int(300 * cropped_rgb.shape[0] / cropped_rgb.shape[1])), Image.Resampling.LANCZOS)
        crop_imgtk_main = ImageTk.PhotoImage(image=crop_img_main)
        self.lbl_esp32_img.imgtk = crop_imgtk_main
        self.lbl_esp32_img.configure(image=crop_imgtk_main)

    def get_roboflow_predictions(self, frame):
        is_success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not is_success:
            return []

        try:
            img_b64 = base64.b64encode(buffer).decode("ascii")
            response = requests.post(
                ROBOFLOW_URL,
                data=img_b64,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=5,
            )
            if response.status_code == 200:
                return response.json().get("predictions", [])
        except Exception as e:
            print(f"[LỖI ROBOFLOW] {e}")
        return []

    def read_plate_text(self, plate_crop):
        try:
            image = cv2.resize(plate_crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD", "/usr/bin/tesseract")
            config = r"--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            raw = pytesseract.image_to_string(thresh, config=config).strip()
            cleaned = re.sub(r"[^A-Z0-9]", "", raw.upper())
            return cleaned if cleaned else None
        except Exception as e:
            print(f"[LỖI TESSERACT] {e}")
            return None

    def clean_extracted_text(self, raw_text: str) -> str:
        lines = raw_text.strip().split('\n')
        cleaned_lines = []
        for line in lines:
            clean_line = re.sub(r'[^A-Z0-9]', '', line.upper())
            if len(clean_line) >= 3:
                cleaned_lines.append(clean_line)

        if len(cleaned_lines) >= 2:
            return f"{cleaned_lines[0]}-{cleaned_lines[1]}"
        elif len(cleaned_lines) == 1:
            return cleaned_lines[0]
        else:
            return "UNKNOWN"

    def on_close(self):
        self.running = False
        self.cap.release()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = SmartParkingValkyrie(root)
    root.mainloop()