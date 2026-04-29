import pyodbc

# Thay đổi thông tin SERVER theo máy của Sensei
DB_CONFIG = {
    'DRIVER': '{ODBC Driver 17 for SQL Server}',
    'SERVER': 'localhost', 
    'DATABASE': 'SmartParking_Valkyrie',
    'UID': 'sa', # Hoặc dùng Trusted_Connection=yes nếu dùng Windows Auth
    'PWD': 'yourpassword' 
}

def get_db_connection():
    try:
        conn_str = f"DRIVER={DB_CONFIG['DRIVER']};SERVER={DB_CONFIG['SERVER']};DATABASE={DB_CONFIG['DATABASE']};UID={DB_CONFIG['UID']};PWD={DB_CONFIG['PWD']}"
        return pyodbc.connect(conn_str)
    except Exception as e:
        print(f"[CẢNH BÁO ĐỎ] Không thể kết nối cơ sở dữ liệu: {e}")
        return None

def get_student_vehicles(ma_sv: str):
    """Truy xuất danh sách biển số và tình trạng xe của một sinh viên"""
    conn = get_db_connection()
    if not conn: return []
    
    cursor = conn.cursor()
    cursor.execute("SELECT BienSo, TinhTrang FROM Xe WHERE MaSV = ?", (ma_sv,))
    rows = cursor.fetchall()
    conn.close()
    return rows