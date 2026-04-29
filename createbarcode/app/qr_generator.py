from __future__ import annotations

import io
import importlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import qrcode
from PIL import Image, ImageDraw, ImageFont

from app.database import bootstrap_database, get_all_students

ROOT_DIR = Path(__file__).resolve().parent.parent
QR_DIR = ROOT_DIR / "qr_codes"
BARCODE_DIR = ROOT_DIR / "barcodes"
QR_SHEET_PATH = QR_DIR / "students_qr_sheet.png"
BARCODE_SHEET_PATH = BARCODE_DIR / "students_barcode_sheet.png"


def _safe_filename(value: str) -> str:
    allowed = []
    for char in value:
        if char.isalnum() or char in {"_", "-"}:
            allowed.append(char)
        elif char.isspace():
            allowed.append("_")
    normalized = "".join(allowed).strip("_")
    return normalized or "student"


def build_qr_payload(student: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "student_id": student["student_id"],
        "full_name": student["full_name"],
        "class_name": student["class_name"],
        "dob": student["dob"],
        "major": student["major"],
        "email": student["email"],
        "phone": student["phone"],
        "ref_code": student["ref_code"],
        "product_code": student["product_code"],
    }


def generate_qr_for_student(student: Dict[str, Any], output_dir: Path = QR_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(build_qr_payload(student), ensure_ascii=False)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_image = qr_image.resize((320, 320), Image.Resampling.LANCZOS)

    card = Image.new("RGB", (420, 440), color=(250, 250, 250))
    card.paste(qr_image, (50, 20))

    draw = ImageDraw.Draw(card)
    font = ImageFont.load_default()
    draw.text((40, 360), f"ID: {student['student_id']}", fill=(20, 20, 20), font=font)
    draw.text((40, 380), f"REFC: {student['ref_code']}", fill=(20, 20, 20), font=font)
    draw.text((40, 400), student["full_name"], fill=(20, 20, 20), font=font)

    filename = f"{student['student_id']}_{_safe_filename(student['full_name'])}.png"
    output_path = output_dir / filename
    card.save(output_path)
    return output_path


def _generate_cards_sheet(
    card_paths: List[Path],
    output_path: Path,
    thumb_width: int,
    thumb_height: int,
    columns: int = 3,
) -> Optional[Path]:
    if not card_paths:
        return None

    padding = 20

    rows = math.ceil(len(card_paths) / columns)
    canvas_width = (columns * thumb_width) + ((columns + 1) * padding)
    canvas_height = (rows * thumb_height) + ((rows + 1) * padding)

    sheet = Image.new("RGB", (canvas_width, canvas_height), color=(245, 245, 245))

    for index, card_path in enumerate(card_paths):
        row = index // columns
        col = index % columns
        x = padding + col * (thumb_width + padding)
        y = padding + row * (thumb_height + padding)

        with Image.open(card_path) as card_image:
            card_thumb = card_image.convert("RGB")
            card_thumb.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            sheet.paste(card_thumb, (x, y))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


def generate_all_qr(output_dir: Path = QR_DIR) -> Dict[str, Any]:
    bootstrap_database(reset=False)
    students = get_all_students()

    qr_paths: List[Path] = []
    for student in students:
        qr_paths.append(generate_qr_for_student(student, output_dir=output_dir))

    sheet_path = _generate_cards_sheet(
        qr_paths,
        output_path=QR_SHEET_PATH,
        thumb_width=300,
        thumb_height=320,
    )

    return {
        "total_students": len(students),
        "generated_files": [str(path) for path in qr_paths],
        "sheet_file": str(sheet_path) if sheet_path else None,
    }


def _build_barcode_image(product_code: str) -> Image.Image:
    barcode_module = importlib.import_module("barcode")
    barcode_writer_module = importlib.import_module("barcode.writer")
    ean13_cls = getattr(barcode_module, "EAN13")
    image_writer_cls = getattr(barcode_writer_module, "ImageWriter")

    ean = ean13_cls(product_code[:12], writer=image_writer_cls())
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
        return barcode_image.convert("RGB")


def generate_barcode_for_student(student: Dict[str, Any], output_dir: Path = BARCODE_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    barcode_image = _build_barcode_image(student["product_code"])
    barcode_image = barcode_image.resize((520, 190), Image.Resampling.LANCZOS)

    card = Image.new("RGB", (560, 380), color=(250, 250, 250))
    card.paste(barcode_image, (20, 18))

    draw = ImageDraw.Draw(card)
    try:
        barcode_number_font = ImageFont.truetype("DejaVuSans.ttf", 26)
    except OSError:
        barcode_number_font = ImageFont.load_default()

    label_font = ImageFont.load_default()
    barcode_number = student["product_code"]
    text_bbox = draw.textbbox((0, 0), barcode_number, font=barcode_number_font)
    text_width = text_bbox[2] - text_bbox[0]
    text_x = max(20, (card.width - text_width) // 2)
    draw.text((text_x, 218), barcode_number, fill=(15, 15, 15), font=barcode_number_font)

    draw.text((20, 285), f"ID: {student['student_id']}", fill=(20, 20, 20), font=label_font)
    draw.text((20, 305), f"REFC: {student['ref_code']}", fill=(20, 20, 20), font=label_font)
    draw.text((20, 325), f"EAN13: {student['product_code']}", fill=(20, 20, 20), font=label_font)
    draw.text((20, 345), student["full_name"], fill=(20, 20, 20), font=label_font)

    filename = f"{student['student_id']}_{_safe_filename(student['full_name'])}_barcode.png"
    output_path = output_dir / filename
    card.save(output_path)
    return output_path


def generate_all_barcodes(output_dir: Path = BARCODE_DIR) -> Dict[str, Any]:
    bootstrap_database(reset=False)
    students = get_all_students()

    barcode_paths: List[Path] = []
    for student in students:
        barcode_paths.append(generate_barcode_for_student(student, output_dir=output_dir))

    sheet_path = _generate_cards_sheet(
        barcode_paths,
        output_path=BARCODE_SHEET_PATH,
        thumb_width=300,
        thumb_height=200,
    )

    return {
        "total_students": len(students),
        "generated_files": [str(path) for path in barcode_paths],
        "sheet_file": str(sheet_path) if sheet_path else None,
    }


def generate_all_codes() -> Dict[str, Any]:
    qr_result = generate_all_qr()
    barcode_result = generate_all_barcodes()
    return {
        "total_students": qr_result["total_students"],
        "qr": qr_result,
        "barcode": barcode_result,
    }


if __name__ == "__main__":
    result = generate_all_codes()
    print(f"Generated code cards for {result['total_students']} students.")
    print(f"QR sheet: {result['qr']['sheet_file']}")
    print(f"Barcode sheet: {result['barcode']['sheet_file']}")
