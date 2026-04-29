from __future__ import annotations

import customtkinter as ctk

if (__package__ or "").startswith("gui"):
    from ..styles import AppStyle
else:
    from gui.styles import AppStyle


class InfoPage(ctk.CTkFrame):
    def __init__(self, parent, main_app):
        super().__init__(parent, fg_color="transparent")
        self.main_app = main_app
        self._build()

    def _build(self):
        shell = ctk.CTkFrame(self, fg_color=AppStyle.CARD_BG, corner_radius=18)
        shell.pack(fill="both", expand=True, padx=10, pady=10)

        hero = ctk.CTkFrame(shell, fg_color=AppStyle.PRIMARY, corner_radius=18)
        hero.pack(fill="x", padx=16, pady=(16, 12))
        ctk.CTkLabel(
            hero,
            text="📘 Hướng Dẫn Sử Dụng Hệ Thống",
            font=("Helvetica", 22, "bold"),
            text_color="white",
        ).pack(anchor="w", padx=18, pady=(18, 4))
        ctk.CTkLabel(
            hero,
            text="Tổng quan quy trình, cảnh báo và cách thao tác nhanh cho quản trị viên.",
            font=AppStyle.BODY_FONT,
            text_color="#E0E7FF",
            wraplength=980,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 18))

        scroll = ctk.CTkScrollableFrame(shell, fg_color="transparent", corner_radius=14)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        sections = [
            (
                "🏗 Cấu trúc hệ thống",
                [
                    "• Dashboard: hiển thị số xe đang đỗ, lượt ra hôm nay và doanh thu hôm nay.",
                    "• Xe Vào: quét barcode/QR/RFID, đối chiếu thông tin và ghi nhận lượt vào.",
                    "• Xe Ra: quét mã, hiển thị hồ sơ ngay lập tức, chụp ảnh ESP32 và đối soát bằng fuzzy logic.",
                    "• Log History: xem toàn bộ lịch sử vào/ra của hệ thống.",
                    "• Thông Tin: trang này chứa hướng dẫn thao tác và các lưu ý khẩn cấp.",
                ],
            ),
            (
                "🚗 Quy trình quét xe vào",
                [
                    "1. Đưa camera vào thẻ/mã QR hoặc barcode của sinh viên.",
                    "2. Hệ thống đọc mã, truy vấn database và tự động điền Họ tên, MSSV, biển số và số dư.",
                    "3. Nếu thẻ bị khóa hoặc xe đã ở trong bãi, hệ thống sẽ cảnh báo ngay.",
                    "4. Khi hợp lệ, xe được ghi log vào bảng LichSuVaoRa và cập nhật danh sách xe đang đỗ.",
                ],
            ),
            (
                "🚦 Quy trình quét xe ra",
                [
                    "1. Quét mã ở cổng ra để hệ thống nhận diện sinh viên/xe tương ứng.",
                    "2. Thông tin người dùng phải xuất hiện ngay trên giao diện trước khi chờ ảnh ESP32.",
                    "3. Camera IoT chụp ảnh biển số, hệ thống so khớp fuzzy và kiểm tra số dư.",
                    "4. Nếu hợp lệ, hệ thống trừ tiền, ghi ThoiGianRa và mở barie.",
                    "5. Nếu sai biển số hoặc lỗi AI quá 3 lần, dùng nút Mở Barie Thủ Công.",
                ],
            ),
            (
                "⚠ Ý nghĩa cảnh báo",
                [
                    "• Xe khóa: xe bị khóa trên hệ thống, không cho ra tự động.",
                    "• Hết tiền: số dư không đủ để thanh toán phí gửi xe.",
                    "• Không khớp biển số: ảnh chụp và biển số đăng ký không trùng nhau.",
                    "• Ngoài giờ hoạt động: hệ thống chỉ cho phép xử lý trong khung 06:00 đến 23:00.",
                ],
            ),
            (
                "🖨 Tạo Barcode / QR Code",
                [
                    "1. Mở tab Quản lý dữ liệu / sinh mã.",
                    "2. Chọn sinh viên cần tạo mã, hoặc tạo hàng loạt cho toàn bộ danh sách.",
                    "3. Mã QR được lưu vào thư mục createbarcode/qr_codes, Barcode lưu vào createbarcode/barcodes.",
                    "4. Khi mở thư mục, hệ thống sẽ dẫn thẳng vào createbarcode/barcodes để không phải tự tìm.",
                ],
            ),
            (
                "🛡 Khẩn cấp & an toàn",
                [
                    "• Mở Barie Thủ Công: dùng khi mạng rớt hoặc AI nhận diện sai quá 3 lần.",
                    "• Backup DB: mỗi lần khởi động, hệ thống tự sao lưu file SQLite chính và chỉ giữ 7 bản mới nhất.",
                    "• Audit log: mọi lần mở thủ công hoặc xóa tài khoản đều được ghi vào security_audit.log.",
                ],
            ),
        ]

        for title, body in sections:
            self._section(scroll, title, body)

        tip = ctk.CTkFrame(scroll, fg_color=AppStyle.SURFACE, corner_radius=14)
        tip.pack(fill="x", pady=(4, 18))
        ctk.CTkLabel(
            tip,
            text="💡 Mẹo: dùng Dashboard để lọc nhanh theo biển số/MSSV, sau đó chuyển qua Xe Ra để xử lý chi tiết.",
            font=AppStyle.BODY_BOLD,
            text_color=AppStyle.TEXT_PRIMARY,
            wraplength=1000,
            justify="left",
        ).pack(anchor="w", padx=16, pady=14)

    def _section(self, parent, title, body_lines):
        card = ctk.CTkFrame(
            parent,
            fg_color=AppStyle.CARD_BG,
            corner_radius=14,
            border_width=1,
            border_color=AppStyle.BORDER,
        )
        card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            card,
            text=title,
            font=("Helvetica", 18, "bold"),
            text_color=AppStyle.PRIMARY,
        ).pack(anchor="w", padx=16, pady=(14, 6))

        for line in body_lines:
            ctk.CTkLabel(
                card,
                text=line,
                font=AppStyle.BODY_FONT,
                text_color=AppStyle.TEXT_SECONDARY,
                wraplength=1000,
                justify="left",
            ).pack(anchor="w", padx=20, pady=2)

        ctk.CTkLabel(card, text="", height=4, fg_color="transparent").pack()
