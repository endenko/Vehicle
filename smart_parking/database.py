"""
Database handler cho SmartParking Valkyrie
Hỗ trợ SQL Server (pyodbc) và SQLite (fallback)
"""
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

import pyodbc

from smart_parking.config import (
    DB_CONFIG,
    DB_BACKEND,
    SQLITE_DB_PATH,
    SQLITE_SCHEMA_PATH,
)


class DatabaseManager:
    """Quản lý kết nối và truy vấn database"""

    def __init__(self):
        self.db_config = DB_CONFIG
        self.backend = DB_BACKEND
        self.sqlite_path = SQLITE_DB_PATH
        self.connection = None
        self.engine = None
        self.lock = threading.Lock()

    def connect(self) -> bool:
        """Kết nối tới database (Ưu tiên SQLite cho bản di động này)"""
        if self.connection:
            return True

        if self.backend == "sqlite":
            return self._connect_sqlite()
        
        if self.backend in {"sqlserver", "mssql", "auto"}:
            if self._connect_sqlserver():
                return True
            if self.backend != "sqlite":
                print("[!] SQL Server không sẵn sàng, chuyển sang SQLite...")
        
        return self._connect_sqlite()

    def _connect_sqlserver(self) -> bool:
        try:
            if self.db_config['TRUSTED_CONNECTION']:
                conn_str = (
                    f"DRIVER={self.db_config['DRIVER']};"
                    f"SERVER={self.db_config['SERVER']};"
                    f"DATABASE={self.db_config['DATABASE']};"
                    "Trusted_Connection=yes"
                )
            else:
                conn_str = (
                    f"DRIVER={self.db_config['DRIVER']};"
                    f"SERVER={self.db_config['SERVER']};"
                    f"DATABASE={self.db_config['DATABASE']};"
                    f"UID={self.db_config['UID']};"
                    f"PWD={self.db_config['PWD']}"
                )

            self.connection = pyodbc.connect(conn_str, timeout=2)
            self.engine = "sqlserver"
            print("[✓] Kết nối SQL Server thành công!")
            return True
        except Exception:
            self.connection = None
            self.engine = None
            return False


    def _connect_sqlite(self) -> bool:
        try:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            self.connection.execute("PRAGMA foreign_keys = ON;")
            self.engine = "sqlite"

            if not self._sqlite_has_tables():
                self._init_sqlite_schema()

            print(f"[✓] Kết nối SQLite thành công: {self.sqlite_path}")
            self.ensure_audit_table()
            return True
        except Exception as e:
            print(f"[✗] Lỗi kết nối SQLite: {e}")
            self.connection = None
            self.engine = None
            return False

    def _sqlite_has_tables(self) -> bool:
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='SinhVien'"
            )
            return cursor.fetchone() is not None
        except Exception:
            return False

    def _init_sqlite_schema(self) -> None:
        if not SQLITE_SCHEMA_PATH.exists():
            print(f"[✗] Không tìm thấy schema SQLite: {SQLITE_SCHEMA_PATH}")
            return

        with SQLITE_SCHEMA_PATH.open("r", encoding="utf-8") as handle:
            schema_sql = handle.read()

        cursor = self.connection.cursor()
        cursor.executescript(schema_sql)
        self.connection.commit()
        print("[✓] Đã khởi tạo SQLite schema + dữ liệu mẫu")

    def _ensure_connection(self) -> bool:
        if self.connection is None:
            return self.connect()
        return True

    def disconnect(self) -> None:
        """Ngắt kết nối"""
        if self.connection:
            self.connection.close()
        self.connection = None
        self.engine = None

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Thực thi query SQL và trả về danh sách dict"""
        if not self._ensure_connection():
            return []
        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(query, params)
                if not cursor.description:
                    self.connection.commit()
                    return []
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            print(f"[✗] Lỗi execute_query: {e}")
            return []

    def get_student_by_id(self, ma_sv: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin sinh viên theo mã SV"""
        if not self._ensure_connection():
            return None

        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    "SELECT MaSV, HoTen, Khoa, Lop, SDT FROM SinhVien WHERE MaSV = ?",
                    (ma_sv,),
                )
                row = cursor.fetchone()

            if row:
                return {
                    'ma_sv': row[0],
                    'ho_ten': row[1],
                    'khoa': row[2],
                    'lop': row[3],
                    'sdt': row[4],
                }
            return None
        except Exception as e:
            print(f"[✗] Lỗi truy vấn sinh viên: {e}")
            return None

    def get_student_vehicles(self, ma_sv: str) -> List[Dict[str, str]]:
        """Lấy danh sách xe của sinh viên"""
        if not self._ensure_connection():
            return []

        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    "SELECT BienSo, LoaiXe, MauSac, TinhTrang FROM Xe WHERE MaSV = ?",
                    (ma_sv,),
                )
                rows = cursor.fetchall()

            vehicles = []
            for row in rows:
                vehicles.append(
                    {
                        'bien_so': row[0],
                        'loai_xe': row[1],
                        'mau_sac': row[2],
                        'tinh_trang': row[3],
                    }
                )
            return vehicles
        except Exception as e:
            print(f"[✗] Lỗi lấy danh sách xe: {e}")
            return []

    def get_rfid_by_student(self, ma_sv: str) -> Optional[Dict[str, Any]]:
        """Lấy thẻ RFID của sinh viên"""
        if not self._ensure_connection():
            return None

        try:
            with self.lock:
                cursor = self.connection.cursor()
                if self.engine == "sqlserver":
                    cursor.execute(
                        "SELECT TOP 1 MaRFID, SoDu, TinhTrang FROM TheRFID WHERE MaSV = ? ORDER BY MaRFID",
                        (ma_sv,),
                    )
                else:
                    cursor.execute(
                        "SELECT MaRFID, SoDu, TinhTrang FROM TheRFID WHERE MaSV = ? ORDER BY MaRFID LIMIT 1",
                        (ma_sv,),
                    )
                row = cursor.fetchone()

            if row:
                return {
                    'ma_rfid': row[0],
                    'so_du': row[1],
                    'tinh_trang': row[2],
                }
            return None
        except Exception as e:
            print(f"[✗] Lỗi lấy RFID: {e}")
            return None

    def add_entry_log(self, ma_rfid: str, bien_so: str, anh_vao_path: str) -> bool:
        """Ghi log vào xe"""
        if not self._ensure_connection():
            return False

        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    """
                    INSERT INTO LichSuVaoRa (MaRFID, BienSo, ThoiGianVao, AnhVao, TrangThai)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (ma_rfid, bien_so, datetime.now(), anh_vao_path, "Đang đỗ"),
                )
                self.connection.commit()
            print(f"[✓] Ghi log vào: {bien_so}")
            return True
        except Exception as e:
            print(f"[✗] Lỗi ghi log vào: {e}")
            return False

    def add_exit_log(self, bien_so: str, anh_ra_path: str, so_tien: int) -> bool:
        """Ghi log ra xe"""
        if not self._ensure_connection():
            return False

        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    """
                    UPDATE LichSuVaoRa
                    SET ThoiGianRa = ?, AnhRa = ?, SoTienTru = ?, TrangThai = 'Đã ra'
                    WHERE BienSo = ? AND TrangThai = 'Đang đỗ'
                    """,
                    (datetime.now(), anh_ra_path, so_tien, bien_so),
                )
                self.connection.commit()
            print(f"[✓] Ghi log ra: {bien_so}")
            return True
        except Exception as e:
            print(f"[✗] Lỗi ghi log ra: {e}")
            return False

    def get_parked_vehicles(self) -> List[Dict[str, Any]]:
        """Lấy danh sách xe đang đỗ"""
        if not self._ensure_connection():
            return []

        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    """
                    SELECT lsr.MaRFID, lsr.BienSo, lsr.ThoiGianVao, sv.HoTen, sv.Lop
                    FROM LichSuVaoRa lsr
                    JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID
                    JOIN SinhVien sv ON rfid.MaSV = sv.MaSV
                    WHERE lsr.TrangThai = 'Đang đỗ'
                    ORDER BY lsr.ThoiGianVao DESC
                    """
                )
                rows = cursor.fetchall()

            parked = []
            for row in rows:
                gio_vao = row[2]
                if isinstance(gio_vao, str):
                    try:
                        gio_vao = datetime.fromisoformat(gio_vao)
                    except ValueError:
                        pass

                parked.append(
                    {
                        'ma_rfid': row[0],
                        'bien_so': row[1],
                        'gio_vao': gio_vao,
                        'ho_ten': row[3],
                        'lop': row[4],
                    }
                )
            return parked
        except Exception as e:
            print(f"[✗] Lỗi lấy xe đang đỗ: {e}")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """Lấy thống kê hệ thống"""
        if not self._ensure_connection():
            return {'parked_count': 0, 'exits_today': 0, 'revenue_today': 0}

        try:
            with self.lock:
                cursor = self.connection.cursor()

                cursor.execute(
                    "SELECT COUNT(*) FROM LichSuVaoRa WHERE TrangThai = 'Đang đỗ'"
                )
                parked_count = cursor.fetchone()[0]

                if self.engine == "sqlserver":
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM LichSuVaoRa
                        WHERE TrangThai = 'Đã ra'
                          AND CAST(ThoiGianRa AS DATE) = CAST(GETDATE() AS DATE)
                        """
                    )
                    exits_today = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        SELECT ISNULL(SUM(SoTienTru), 0) FROM LichSuVaoRa
                        WHERE CAST(ThoiGianRa AS DATE) = CAST(GETDATE() AS DATE)
                        """
                    )
                    revenue_today = cursor.fetchone()[0]
                else:
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM LichSuVaoRa
                        WHERE TrangThai = 'Đã ra'
                          AND date(ThoiGianRa) = date('now')
                        """
                    )
                    exits_today = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        SELECT COALESCE(SUM(SoTienTru), 0) FROM LichSuVaoRa
                        WHERE date(ThoiGianRa) = date('now')
                        """
                    )
                    revenue_today = cursor.fetchone()[0]

            return {
                'parked_count': parked_count,
                'exits_today': exits_today,
                'revenue_today': revenue_today,
            }
        except Exception as e:
            print(f"[✗] Lỗi lấy thống kê: {e}")
            return {'parked_count': 0, 'exits_today': 0, 'revenue_today': 0}

    def get_student_by_rfid(self, ma_rfid: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin sinh viên theo mã RFID"""
        if not self._ensure_connection():
            return None

        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    """
                    SELECT sv.MaSV, sv.HoTen, sv.Khoa, sv.Lop, sv.SDT, rfid.SoDu, rfid.TinhTrang
                    FROM TheRFID rfid
                    JOIN SinhVien sv ON rfid.MaSV = sv.MaSV
                    WHERE rfid.MaRFID = ?
                    """,
                    (ma_rfid,),
                )
                row = cursor.fetchone()

            if row:
                return {
                    'ma_sv': row[0],
                    'ho_ten': row[1],
                    'khoa': row[2],
                    'lop': row[3],
                    'sdt': row[4],
                    'so_du': row[5],
                    'tinh_trang': row[6],
                }
            return None
        except Exception as e:
            print(f"[✗] Lỗi lấy sinh viên theo RFID: {e}")
            return None

    def get_rfid_by_code(self, ma_rfid: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin RFID theo mã"""
        if not self._ensure_connection():
            return None

        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    "SELECT MaRFID, MaSV, SoDu, TinhTrang FROM TheRFID WHERE MaRFID = ?",
                    (ma_rfid,),
                )
                row = cursor.fetchone()

            if row:
                return {
                    'ma_rfid': row[0],
                    'ma_sv': row[1],
                    'so_du': row[2],
                    'tinh_trang': row[3],
                }
            return None
        except Exception as e:
            print(f"[✗] Lỗi lấy RFID theo mã: {e}")
            return None

    def update_rfid_balance(self, ma_rfid: str, delta: int) -> bool:
        """Cập nhật số dư RFID (delta âm để trừ tiền)"""
        if not self._ensure_connection():
            return False

        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    "UPDATE TheRFID SET SoDu = SoDu + ? WHERE MaRFID = ?",
                    (delta, ma_rfid),
                )
                self.connection.commit()
            return True
        except Exception as e:
            print(f"[✗] Lỗi cập nhật số dư RFID: {e}")
            return False

    def get_active_entry_by_plate(self, bien_so: str) -> Optional[Dict[str, Any]]:
        """Lấy giao dịch đang đỗ theo biển số"""
        if not self._ensure_connection():
            return None

        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    """
                    SELECT lsr.ID, lsr.MaRFID, lsr.BienSo, lsr.ThoiGianVao, lsr.AnhVao,
                           sv.HoTen, sv.MaSV, sv.Khoa, sv.Lop, sv.SDT
                    FROM LichSuVaoRa lsr
                    JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID
                    JOIN SinhVien sv ON rfid.MaSV = sv.MaSV
                    WHERE lsr.BienSo = ? AND lsr.TrangThai = 'Đang đỗ'
                    ORDER BY lsr.ThoiGianVao DESC
                    """,
                    (bien_so,),
                )
                row = cursor.fetchone()

            if row:
                return {
                    'transaction_id': row[0],
                    'ma_rfid': row[1],
                    'bien_so': row[2],
                    'thoi_gian_vao': row[3],
                    'anh_vao': row[4],
                    'ho_ten': row[5],
                    'ma_sv': row[6],
                    'khoa': row[7],
                    'lop': row[8],
                    'sdt': row[9],
                }
            return None
        except Exception as e:
            print(f"[✗] Lỗi lấy giao dịch đang đỗ: {e}")
            return None

    def get_active_entry_by_rfid(self, ma_rfid: str) -> Optional[Dict[str, Any]]:
        """Lấy giao dịch đang đỗ theo RFID."""
        if not self._ensure_connection():
            return None

        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    """
                    SELECT lsr.ID, lsr.MaRFID, lsr.BienSo, lsr.ThoiGianVao, lsr.AnhVao,
                           sv.HoTen, sv.MaSV, sv.Khoa, sv.Lop, sv.SDT
                    FROM LichSuVaoRa lsr
                    JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID
                    JOIN SinhVien sv ON rfid.MaSV = sv.MaSV
                    WHERE lsr.MaRFID = ? AND lsr.TrangThai = 'Đang đỗ'
                    ORDER BY lsr.ThoiGianVao DESC
                    """,
                    (ma_rfid,),
                )
                row = cursor.fetchone()

            if row:
                return {
                    'transaction_id': row[0],
                    'ma_rfid': row[1],
                    'bien_so': row[2],
                    'thoi_gian_vao': row[3],
                    'anh_vao': row[4],
                    'ho_ten': row[5],
                    'ma_sv': row[6],
                    'khoa': row[7],
                    'lop': row[8],
                    'sdt': row[9],
                }
            return None
        except Exception as e:
            print(f"[✗] Lỗi lấy giao dịch theo RFID: {e}")
            return None

    def get_parking_history(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Lấy lịch sử vào/ra"""
        if not self._ensure_connection():
            return []

        try:
            with self.lock:
                cursor = self.connection.cursor()
                limit_clause = "?" if self.engine != "sqlserver" else "?"
                query = (
                    "SELECT lsr.ID, lsr.BienSo, lsr.ThoiGianVao, lsr.ThoiGianRa, lsr.TrangThai, lsr.SoTienTru, "
                    "sv.HoTen, sv.MaSV, sv.Lop, sv.Khoa, rfid.SoDu, rfid.TinhTrang "
                    "FROM LichSuVaoRa lsr "
                    "JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID "
                    "JOIN SinhVien sv ON rfid.MaSV = sv.MaSV "
                    "ORDER BY lsr.ID DESC "
                    f"LIMIT {limit_clause}"
                )

                if self.engine == "sqlserver":
                    query = (
                        "SELECT TOP (?) lsr.ID, lsr.BienSo, lsr.ThoiGianVao, lsr.ThoiGianRa, lsr.TrangThai, lsr.SoTienTru, "
                        "sv.HoTen, sv.MaSV, sv.Lop, sv.Khoa, rfid.SoDu, rfid.TinhTrang "
                        "FROM LichSuVaoRa lsr "
                        "JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID "
                        "JOIN SinhVien sv ON rfid.MaSV = sv.MaSV "
                        "ORDER BY lsr.ID DESC"
                    )

                cursor.execute(query, (limit,))
                rows = cursor.fetchall()

            history = []
            for row in rows:
                history.append(
                    {
                        'transaction_id': row[0],
                        'license_plate': row[1],
                        'time_in': row[2],
                        'time_out': row[3],
                        'status': row[4],
                        'fee': row[5],
                        'owner_name': row[6],
                        'owner_identity': row[7],
                        'owner_class': row[8],
                        'owner_major': row[9],
                        'owner_balance': row[10],
                        'rfid_status': row[11],
                    }
                )
            return history
        except Exception as e:
            print(f"[✗] Lỗi lấy lịch sử: {e}")
            return []

    def get_active_transactions(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Lấy danh sách xe đang đỗ"""
        if not self._ensure_connection():
            return []

        try:
            with self.lock:
                cursor = self.connection.cursor()
                limit_clause = "?" if self.engine != "sqlserver" else "?"
                query = (
                    "SELECT lsr.ID, lsr.BienSo, lsr.ThoiGianVao, lsr.TrangThai, "
                    "sv.HoTen, sv.MaSV, sv.Lop, sv.Khoa "
                    "FROM LichSuVaoRa lsr "
                    "JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID "
                    "JOIN SinhVien sv ON rfid.MaSV = sv.MaSV "
                    "WHERE lsr.TrangThai = 'Đang đỗ' "
                    "ORDER BY lsr.ThoiGianVao DESC "
                    f"LIMIT {limit_clause}"
                )
                if self.engine == "sqlserver":
                    query = (
                        "SELECT TOP (?) lsr.ID, lsr.BienSo, lsr.ThoiGianVao, lsr.TrangThai, "
                        "sv.HoTen, sv.MaSV, sv.Lop, sv.Khoa "
                        "FROM LichSuVaoRa lsr "
                        "JOIN TheRFID rfid ON lsr.MaRFID = rfid.MaRFID "
                        "JOIN SinhVien sv ON rfid.MaSV = sv.MaSV "
                        "WHERE lsr.TrangThai = 'Đang đỗ' "
                        "ORDER BY lsr.ThoiGianVao DESC"
                    )

                cursor.execute(query, (limit,))
                rows = cursor.fetchall()

            active = []
            for row in rows:
                active.append(
                    {
                        'transaction_id': row[0],
                        'license_plate': row[1],
                        'time_in': row[2],
                        'status': row[3],
                        'owner_name': row[4],
                        'owner_identity': row[5],
                        'owner_class': row[6],
                        'owner_major': row[7],
                    }
                )
            return active
        except Exception as e:
            print(f"[✗] Lỗi lấy xe đang đỗ: {e}")
            return []

    # ── Audit Table (Bảng Kiểm toán) ─────────────────────────────────────────

    def ensure_audit_table(self) -> None:
        """Tự động tạo bảng KetQuaQuyetDinh nếu chưa tồn tại.
        
        FK liên kết: MaSV → SinhVien(MaSV), BienSo → Xe(BienSo)
        BienSoOCR: Biển số đọc bởi OCR (có thể không khớp bất kỳ xe nào)
        LoaiLane: IN hoặc OUT
        """
        if not self._ensure_connection():
            return
        try:
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS KetQuaQuyetDinh (
                        ID INTEGER PRIMARY KEY AUTOINCREMENT,
                        MaSV TEXT,
                        HoTen TEXT,
                        BienSo TEXT,
                        BienSoOCR TEXT,
                        LoaiLane TEXT DEFAULT 'IN',
                        KetQua TEXT,
                        ThoiGian TEXT DEFAULT (datetime('now')),
                        FOREIGN KEY (MaSV) REFERENCES SinhVien(MaSV),
                        FOREIGN KEY (BienSo) REFERENCES Xe(BienSo)
                    )
                """)
                self.connection.commit()
        except Exception as e:
            print(f"[✗] Lỗi tạo bảng KetQuaQuyetDinh: {e}")

    def log_audit_decision(
        self,
        ma_sv: str,
        ho_ten: str,
        bien_so: str,
        ket_qua: str,
        bien_so_ocr: str = "",
        lane: str = "IN",
    ) -> bool:
        """Ghi log quyết định vào bảng KetQuaQuyetDinh.
        
        Args:
            ma_sv: Mã sinh viên (FK → SinhVien.MaSV)
            ho_ten: Họ tên sinh viên
            bien_so: Biển số đăng ký trong DB (FK → Xe.BienSo), NULL nếu chưa xác định
            ket_qua: Kết quả quyết định (Cho phép/Từ chối/Cảnh báo + lý do)
            bien_so_ocr: Biển số đọc từ Google Vision OCR (raw text, không ràng buộc FK)
            lane: Loại làn - "IN" hoặc "OUT"
        
        Được gọi ở MỌI nhánh rẽ của thuật toán (thành công, lỗi, cảnh báo)
        trước khi trả về HTTP Response.
        """
        if not self._ensure_connection():
            return False
        try:
            # bien_so phải tồn tại trong bảng Xe (FK constraint)
            # Nếu bien_so không hợp lệ → set NULL để tránh FK violation
            bien_so_fk = bien_so if bien_so and bien_so != "UNKNOWN" and bien_so != "ERROR" else None
            
            with self.lock:
                cursor = self.connection.cursor()
                cursor.execute(
                    "INSERT INTO KetQuaQuyetDinh (MaSV, HoTen, BienSo, BienSoOCR, LoaiLane, KetQua) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (ma_sv, ho_ten, bien_so_fk, bien_so_ocr, lane, ket_qua),
                )
                self.connection.commit()
            print(f"[📋] Audit [{lane}]: {ma_sv} | {ket_qua}")
            return True
        except Exception as e:
            print(f"[✗] Lỗi ghi audit: {e}")
            return False

# Global instance
db_manager = DatabaseManager()

