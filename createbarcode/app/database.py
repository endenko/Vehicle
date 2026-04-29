from __future__ import annotations

import json
import re
import sqlite3
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "students.db"
SEED_PATH = ROOT_DIR / "data" / "students_seed.json"


def _build_ref_code(student_id: str) -> str:
    return f"REFC-{student_id}"


def _build_ean13_check_digit(base12: str) -> str:
    odd_sum = sum(int(base12[index]) for index in range(0, 12, 2))
    even_sum = sum(int(base12[index]) for index in range(1, 12, 2))
    check_digit = (10 - ((odd_sum + (3 * even_sum)) % 10)) % 10
    return str(check_digit)


def _build_product_code(student_id: str) -> str:
    normalized_id = re.sub(r"[^A-Z0-9]", "", student_id.upper()) or "UNKNOWN"
    hash_suffix = zlib.crc32(normalized_id.encode("utf-8")) % 1_000_000_000
    base12 = f"893{hash_suffix:09d}"
    return f"{base12}{_build_ean13_check_digit(base12)}"


def _normalize_product_code(product_code: str) -> str:
    digits = re.sub(r"\D", "", product_code)
    if len(digits) == 12:
        return f"{digits}{_build_ean13_check_digit(digits)}"
    return digits


def _ensure_schema_columns(connection: sqlite3.Connection) -> None:
    table_info_rows = connection.execute("PRAGMA table_info(students)").fetchall()
    existing_columns = {str(row[1]) for row in table_info_rows}

    if "product_code" not in existing_columns:
        connection.execute("ALTER TABLE students ADD COLUMN product_code TEXT")

    student_rows = connection.execute(
        "SELECT student_id, product_code FROM students"
    ).fetchall()
    for student_id, product_code in student_rows:
        if product_code:
            continue
        generated_product_code = _build_product_code(str(student_id))
        connection.execute(
            "UPDATE students SET product_code = ? WHERE student_id = ?",
            (generated_product_code, student_id),
        )


def create_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()

    with create_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                class_name TEXT NOT NULL,
                dob TEXT NOT NULL,
                major TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                ref_code TEXT NOT NULL UNIQUE,
                product_code TEXT UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_schema_columns(conn)
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_students_ref_code
            ON students(ref_code)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_students_product_code
            ON students(product_code)
            """
        )
        conn.commit()


def load_seed_data(seed_path: Path = SEED_PATH) -> List[Dict[str, str]]:
    if not seed_path.exists():
        return []

    with seed_path.open("r", encoding="utf-8") as seed_file:
        raw_students = json.load(seed_file)

    students: List[Dict[str, str]] = []
    for item in raw_students:
        student_id = str(item.get("student_id", "")).strip().upper()
        if not student_id:
            continue

        students.append(
            {
                "student_id": student_id,
                "full_name": str(item.get("full_name", "")).strip(),
                "class_name": str(item.get("class_name", "")).strip(),
                "dob": str(item.get("dob", "")).strip(),
                "major": str(item.get("major", "")).strip(),
                "email": str(item.get("email", "")).strip(),
                "phone": str(item.get("phone", "")).strip(),
                "ref_code": _build_ref_code(student_id),
                "product_code": _build_product_code(student_id),
            }
        )

    return students


def seed_students(students: Optional[List[Dict[str, str]]] = None) -> int:
    students = students if students is not None else load_seed_data()
    if not students:
        return 0

    rows = [
        (
            student["student_id"],
            student["full_name"],
            student["class_name"],
            student["dob"],
            student["major"],
            student["email"],
            student["phone"],
            student["ref_code"],
            student["product_code"],
        )
        for student in students
    ]

    with create_connection() as conn:
        conn.executemany(
            """
            INSERT INTO students (
                student_id, full_name, class_name, dob,
                major, email, phone, ref_code, product_code
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(student_id) DO UPDATE SET
                full_name = excluded.full_name,
                class_name = excluded.class_name,
                dob = excluded.dob,
                major = excluded.major,
                email = excluded.email,
                phone = excluded.phone,
                ref_code = excluded.ref_code,
                product_code = excluded.product_code
            """,
            rows,
        )
        conn.commit()

    return len(rows)


def bootstrap_database(reset: bool = False) -> int:
    init_db(reset=reset)
    return seed_students()


def get_all_students() -> List[Dict[str, Any]]:
    with create_connection() as conn:
        rows = conn.execute(
            """
            SELECT student_id, full_name, class_name, dob, major, email, phone, ref_code, product_code
            FROM students
            ORDER BY student_id
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_student_by_id(student_id: str) -> Optional[Dict[str, Any]]:
    normalized_id = student_id.strip().upper()
    with create_connection() as conn:
        row = conn.execute(
            """
            SELECT student_id, full_name, class_name, dob, major, email, phone, ref_code, product_code
            FROM students
            WHERE student_id = ?
            """,
            (normalized_id,),
        ).fetchone()

    return dict(row) if row else None


def get_student_by_ref_code(ref_code: str) -> Optional[Dict[str, Any]]:
    normalized_ref = ref_code.strip().upper()
    with create_connection() as conn:
        row = conn.execute(
            """
            SELECT student_id, full_name, class_name, dob, major, email, phone, ref_code, product_code
            FROM students
            WHERE ref_code = ?
            """,
            (normalized_ref,),
        ).fetchone()

    return dict(row) if row else None


def get_student_by_product_code(product_code: str) -> Optional[Dict[str, Any]]:
    normalized_product_code = _normalize_product_code(product_code)
    if len(normalized_product_code) != 13:
        return None

    with create_connection() as conn:
        row = conn.execute(
            """
            SELECT student_id, full_name, class_name, dob, major, email, phone, ref_code, product_code
            FROM students
            WHERE product_code = ?
            """,
            (normalized_product_code,),
        ).fetchone()

    return dict(row) if row else None
