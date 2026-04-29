"""
createbarcode/generator.py
Module sinh mã QR và Barcode (EAN-13) cho hệ thống SmartParking.
Sử dụng thư viện: qrcode, python-barcode, Pillow.

Đầu vào: dict {"MSSV": "...", "BienSo": "...", "HoTen": "..."}
Đầu ra : File ảnh {MSSV}_{BienSo}.png trong createbarcode/barcodes/
"""
from __future__ import annotations

import io
import json
import os
import re
import zlib
from pathlib import Path
from typing import Any, Dict, Optional

import qrcode
from PIL import Image, ImageDraw, ImageFont

# ── Thư mục gốc ──────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent
BARCODES_DIR = ROOT_DIR / "barcodes"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _safe_filename(value: str) -> str:
    """Chuẩn hóa tên file (bỏ ký tự đặc biệt)."""
    allowed = []
    for char in value:
        if char.isalnum() or char in {"_", "-"}:
            allowed.append(char)
        elif char.isspace():
            allowed.append("_")
    return "".join(allowed).strip("_") or "unknown"


def _build_ean13_check_digit(base12: str) -> str:
    """Tính check-digit cho EAN-13."""
    odd_sum = sum(int(base12[i]) for i in range(0, 12, 2))
    even_sum = sum(int(base12[i]) for i in range(1, 12, 2))
    check_digit = (10 - ((odd_sum + (3 * even_sum)) % 10)) % 10
    return str(check_digit)


def _build_product_code(mssv: str) -> str:
    """Tạo EAN-13 product code từ MSSV."""
    normalized = re.sub(r"[^A-Z0-9]", "", mssv.upper()) or "UNKNOWN"
    hash_suffix = zlib.crc32(normalized.encode("utf-8")) % 1_000_000_000
    base12 = f"893{hash_suffix:09d}"
    return f"{base12}{_build_ean13_check_digit(base12)}"


def _get_font(size: int = 14):
    """Lấy font, fallback về default nếu không tìm thấy."""
    for font_name in ["DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ── Sinh QR Code ──────────────────────────────────────────────────────────────
def generate_qr(data: dict, output_dir: str = None) -> Optional[str]:
    """
    Sinh mã QR từ dictionary.

    Args:
        data: dict chứa ít nhất {"MSSV": "...", "BienSo": "...", "HoTen": "..."}
        output_dir: Thư mục đầu ra (mặc định: createbarcode/barcodes/)

    Returns:
        Đường dẫn file ảnh đã tạo, hoặc None nếu lỗi.
    """
    out_dir = Path(output_dir) if output_dir else BARCODES_DIR
    if not os.path.exists(str(out_dir)):
        os.makedirs(str(out_dir))

    mssv = str(data.get("MSSV", "")).strip()
    bien_so = str(data.get("BienSo", "")).strip()
    ho_ten = str(data.get("HoTen", "")).strip()

    if not mssv:
        return None

    # Payload QR
    payload = json.dumps(data, ensure_ascii=False, indent=None)

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_image = qr_image.resize((300, 300), Image.Resampling.LANCZOS)

    # Tạo card
    card = Image.new("RGB", (400, 440), color=(250, 250, 250))
    card.paste(qr_image, (50, 20))

    draw = ImageDraw.Draw(card)
    font_label = _get_font(13)
    font_title = _get_font(15)

    draw.text((40, 335), f"MSSV: {mssv}", fill=(20, 20, 20), font=font_title)
    draw.text((40, 360), f"Biển số: {bien_so}", fill=(20, 20, 20), font=font_label)
    draw.text((40, 385), f"Họ tên: {ho_ten}", fill=(20, 20, 20), font=font_label)
    draw.text((40, 410), "QR Code — SmartParking", fill=(120, 120, 120), font=font_label)

    # Lưu file
    safe_plate = _safe_filename(bien_so) if bien_so else "noplate"
    filename = f"{mssv}_{safe_plate}_qr.png"
    output_path = out_dir / filename
    card.save(str(output_path))
    return str(output_path)


# ── Sinh Barcode (EAN-13) ─────────────────────────────────────────────────────
def generate_barcode(data: dict, output_dir: str = None) -> Optional[str]:
    """
    Sinh mã Barcode EAN-13 từ dictionary.

    Args:
        data: dict chứa ít nhất {"MSSV": "...", "BienSo": "...", "HoTen": "..."}
        output_dir: Thư mục đầu ra (mặc định: createbarcode/barcodes/)

    Returns:
        Đường dẫn file ảnh đã tạo, hoặc None nếu lỗi.
    """
    out_dir = Path(output_dir) if output_dir else BARCODES_DIR
    if not os.path.exists(str(out_dir)):
        os.makedirs(str(out_dir))

    mssv = str(data.get("MSSV", "")).strip()
    bien_so = str(data.get("BienSo", "")).strip()
    ho_ten = str(data.get("HoTen", "")).strip()

    if not mssv:
        return None

    product_code = _build_product_code(mssv)

    # Sinh barcode bằng python-barcode
    import barcode as barcode_lib
    from barcode.writer import ImageWriter

    ean = barcode_lib.EAN13(product_code[:12], writer=ImageWriter())
    buffer = io.BytesIO()
    ean.write(
        buffer,
        options={
            "module_width": 0.34,
            "module_height": 26,
            "quiet_zone": 6.0,
            "write_text": False,
            "dpi": 300,
        },
    )
    buffer.seek(0)
    with Image.open(buffer) as barcode_image:
        barcode_img = barcode_image.convert("RGB")
    barcode_img = barcode_img.resize((500, 180), Image.Resampling.LANCZOS)

    # Tạo card
    card = Image.new("RGB", (540, 380), color=(250, 250, 250))
    card.paste(barcode_img, (20, 18))

    draw = ImageDraw.Draw(card)
    font_label = _get_font(13)
    font_barcode = _get_font(22)
    font_title = _get_font(15)

    # Số barcode ở giữa
    text_bbox = draw.textbbox((0, 0), product_code, font=font_barcode)
    text_width = text_bbox[2] - text_bbox[0]
    text_x = max(20, (card.width - text_width) // 2)
    draw.text((text_x, 210), product_code, fill=(15, 15, 15), font=font_barcode)

    draw.text((20, 260), f"MSSV: {mssv}", fill=(20, 20, 20), font=font_title)
    draw.text((20, 290), f"Biển số: {bien_so}", fill=(20, 20, 20), font=font_label)
    draw.text((20, 315), f"Họ tên: {ho_ten}", fill=(20, 20, 20), font=font_label)
    draw.text((20, 345), f"EAN13 Barcode — SmartParking", fill=(120, 120, 120), font=font_label)

    # Lưu file
    safe_plate = _safe_filename(bien_so) if bien_so else "noplate"
    filename = f"{mssv}_{safe_plate}_barcode.png"
    output_path = out_dir / filename
    card.save(str(output_path))
    return str(output_path)


# ── Tiện ích ──────────────────────────────────────────────────────────────────
def generate_both(data: dict, output_dir: str = None) -> Dict[str, Optional[str]]:
    """Sinh cả QR và Barcode cùng lúc."""
    return {
        "qr": generate_qr(data, output_dir),
        "barcode": generate_barcode(data, output_dir),
    }


if __name__ == "__main__":
    # Demo
    test_data = {
        "MSSV": "SV21001",
        "BienSo": "43A1-12345",
        "HoTen": "Nguyễn Văn An",
        "Lop": "21SPT1",
        "Khoa": "Sư phạm Tin",
    }
    result = generate_both(test_data)
    print(f"QR: {result['qr']}")
    print(f"Barcode: {result['barcode']}")
