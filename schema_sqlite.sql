-- SmartParking Valkyrie Database Schema
-- SQLite Script (Fallback)

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS LichSuVaoRa;
DROP TABLE IF EXISTS TheRFID;
DROP TABLE IF EXISTS Xe;
DROP TABLE IF EXISTS SinhVien;

CREATE TABLE SinhVien (
    MaSV TEXT PRIMARY KEY,
    HoTen TEXT NOT NULL,
    Khoa TEXT,
    Lop TEXT,
    SDT TEXT,
    NgayTao TEXT DEFAULT (datetime('now'))
);

CREATE TABLE Xe (
    BienSo TEXT PRIMARY KEY,
    MaSV TEXT NOT NULL,
    LoaiXe TEXT,
    MauSac TEXT,
    TinhTrang TEXT DEFAULT 'Không Khóa',
    NgayTao TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (MaSV) REFERENCES SinhVien(MaSV)
);

CREATE TABLE TheRFID (
    MaRFID TEXT PRIMARY KEY,
    MaSV TEXT NOT NULL,
    SoDu INTEGER DEFAULT 0,
    TinhTrang TEXT DEFAULT 'Hoạt động',
    NgayTao TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (MaSV) REFERENCES SinhVien(MaSV)
);

CREATE TABLE LichSuVaoRa (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    MaRFID TEXT,
    BienSo TEXT,
    ThoiGianVao TEXT NOT NULL,
    AnhVao TEXT,
    ThoiGianRa TEXT,
    AnhRa TEXT,
    SoTienTru INTEGER DEFAULT 0,
    TrangThai TEXT DEFAULT 'Đang đỗ',
    NgayTao TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (MaRFID) REFERENCES TheRFID(MaRFID),
    FOREIGN KEY (BienSo) REFERENCES Xe(BienSo)
);

CREATE INDEX IX_Xe_MaSV ON Xe(MaSV);
CREATE INDEX IX_TheRFID_MaSV ON TheRFID(MaSV);
CREATE INDEX IX_LichSuVaoRa_BienSo ON LichSuVaoRa(BienSo);
CREATE INDEX IX_LichSuVaoRa_TrangThai ON LichSuVaoRa(TrangThai);
CREATE INDEX IX_LichSuVaoRa_ThoiGianVao ON LichSuVaoRa(ThoiGianVao);

-- Bảng Kiểm toán (Audit Table) — Ghi lại MỌI quyết định của hệ thống
-- FK liên kết trực tiếp tới SinhVien(MaSV) và Xe(BienSo) trong smart_parking.db
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
);

CREATE INDEX IF NOT EXISTS IX_KetQuaQuyetDinh_MaSV ON KetQuaQuyetDinh(MaSV);
CREATE INDEX IF NOT EXISTS IX_KetQuaQuyetDinh_BienSo ON KetQuaQuyetDinh(BienSo);
CREATE INDEX IF NOT EXISTS IX_KetQuaQuyetDinh_ThoiGian ON KetQuaQuyetDinh(ThoiGian);

INSERT INTO SinhVien (MaSV, HoTen, Khoa, Lop, SDT) VALUES
('SV21001', 'Nguyễn Văn An', 'Sư phạm Tin', '21SPT1', '0901234501'),
('SV21002', 'Trần Thị Bích', 'Sư phạm Tin', '21SPT1', '0901234502'),
('SV21003', 'Lê Hoàng Cường', 'CNTT', '21IT2', '0901234503'),
('SV21004', 'Phạm Mỹ Dung', 'Sư phạm Tin', '22SPT1', '0901234504'),
('SV21005', 'Vũ Đức Anh', 'Sư phạm Lý', '21SPL', '0901234505'),
('SV21006', 'Đặng Thanh Hải', 'Sư phạm Tin', '21SPT2', '0901234506'),
('SV21007', 'Bùi Tấn Gia', 'CNTT', '20IT3', '0901234507'),
('SV21008', 'Hồ Xuân Hương', 'Sư phạm Ngữ Văn', '22SPV', '0901234508'),
('SV21009', 'Ngô Hữu Trí', 'Sư phạm Hóa', '21SPH', '0901234509'),
('SV21010', 'Đoàn Văn Trọng', 'Sư phạm Tin', '21SPT1', '0901234510'),
('SV21011', 'Lý Thảo My', 'Sư phạm Sinh', '23SPS', '0901234511'),
('SV21012', 'Châu Tấn Phát', 'CNTT', '21IT1', '0901234512'),
('SV21013', 'Đỗ Quyên Quyên', 'Sư phạm Lịch Sử', '22SPLS', '0901234513'),
('SV21014', 'Võ Minh Quân', 'Sư phạm Địa', '21SPD', '0901234514'),
('SV21015', 'Thái Tuấn Kiệt', 'Sư phạm Tin', '21SPT2', '0901234515'),
('SV21016', 'Phan Gia Bảo', 'CNTT', '22IT1', '0901234516'),
('SV21017', 'Nguyễn Thảo Linh', 'Kinh tế', '22KT1', '0901234517'),
('SV21018', 'Trần Đức Huy', 'CNTT', '23IT1', '0901234518'),
('SV21019', 'Võ Lan Phương', 'Ngoại ngữ', '21NN1', '0901234519'),
('SV21020', 'Lê Minh Khoa', 'CNTT', '20IT1', '0901234520');

INSERT INTO Xe (BienSo, MaSV, LoaiXe, MauSac, TinhTrang) VALUES
('43A1-12345', 'SV21001', 'Honda AirBlade', 'Đen', 'Không Khóa'),
('43B1-55522', 'SV21001', 'Yamaha Sirius', 'Đỏ', 'Khóa'),
('92H1-77899', 'SV21002', 'Honda Wave', 'Xanh', 'Không Khóa'),
('73K1-34211', 'SV21003', 'Yamaha Exciter', 'Trắng', 'Không Khóa'),
('43C1-99800', 'SV21004', 'Honda Vision', 'Trắng', 'Không Khóa'),
('74F1-11123', 'SV21005', 'Honda Winner X', 'Đen nhám', 'Không Khóa'),
('43D1-45678', 'SV21006', 'Yamaha Grande', 'Hồng', 'Không Khóa'),
('43D1-45679', 'SV21006', 'VinFast Feliz', 'Trắng', 'Không Khóa'),
('75G1-66788', 'SV21007', 'Honda Lead', 'Vàng', 'Không Khóa'),
('43E1-22344', 'SV21008', 'Vespa', 'Xám', 'Khóa'),
('92N1-55433', 'SV21009', 'Honda SH', 'Trắng', 'Không Khóa'),
('73M1-88912', 'SV21010', 'Yamaha NVX', 'Xanh GP', 'Không Khóa'),
('43F1-33455', 'SV21011', 'Honda Wave RSX', 'Đen', 'Không Khóa'),
('74L1-77654', 'SV21012', 'Suzuki Raider', 'Đen', 'Không Khóa'),
('92K1-12399', 'SV21013', 'Honda PCX', 'Xám', 'Không Khóa'),
('43G1-98765', 'SV21014', 'Yamaha Jupiter', 'Xanh', 'Không Khóa'),
('75H1-44566', 'SV21015', 'Honda Vario', 'Trắng', 'Không Khóa'),
('43A1-00001', 'SV21003', 'Honda Cub', 'Xanh nhạt', 'Không Khóa'),
('43H1-11223', 'SV21016', 'Honda Click', 'Đen', 'Không Khóa'),
('43H1-11224', 'SV21017', 'Yamaha Janus', 'Trắng', 'Không Khóa'),
('92P1-77881', 'SV21018', 'Honda Blade', 'Đỏ', 'Không Khóa'),
('75K1-90909', 'SV21019', 'Suzuki Address', 'Xanh', 'Không Khóa'),
('43K1-20202', 'SV21020', 'VinFast Evo', 'Đen', 'Không Khóa');

INSERT INTO TheRFID (MaRFID, MaSV, SoDu, TinhTrang) VALUES
('RFID_UED_100', 'SV21001', 94985, 'Hoạt động'),
('RFID_UED_101', 'SV21002', 174788, 'Hoạt động'),
('RFID_UED_102', 'SV21003', 160415, 'Hoạt động'),
('RFID_UED_103', 'SV21004', 71604, 'Hoạt động'),
('RFID_UED_104', 'SV21005', 13402, 'Hoạt động'),
('RFID_UED_105', 'SV21006', 132361, 'Hoạt động'),
('RFID_UED_106', 'SV21007', 0, 'Hoạt động'),
('RFID_UED_107', 'SV21008', 184672, 'Khóa'),
('RFID_UED_108', 'SV21009', 24406, 'Hoạt động'),
('RFID_UED_109', 'SV21010', 150891, 'Hoạt động'),
('RFID_UED_110', 'SV21011', 62384, 'Hoạt động'),
('RFID_UED_111', 'SV21012', 2000, 'Hoạt động'),
('RFID_UED_112', 'SV21013', 62364, 'Hoạt động'),
('RFID_UED_113', 'SV21016', 55000, 'Hoạt động'),
('RFID_UED_114', 'SV21017', 1000, 'Hoạt động'),
('RFID_UED_115', 'SV21020', 89000, 'Hoạt động');

INSERT INTO LichSuVaoRa (MaRFID, BienSo, ThoiGianVao, AnhVao, ThoiGianRa, AnhRa, SoTienTru, TrangThai) VALUES
('RFID_UED_100', '43A1-12345', '2026-04-19 07:00:00', '/storage/in/43A1-12345_0.jpg', '2026-04-19 12:00:00', '/storage/out/43A1-12345_0.jpg', 3000, 'Đã ra'),
('RFID_UED_100', '43B1-55522', '2026-04-19 07:15:00', '/storage/in/43B1-55522_1.jpg', '2026-04-19 12:15:00', '/storage/out/43B1-55522_1.jpg', 3000, 'Đã ra'),
('RFID_UED_101', '92H1-77899', '2026-04-19 07:30:00', '/storage/in/92H1-77899_2.jpg', '2026-04-19 08:30:00', '/storage/out/92H1-77899_2.jpg', 3000, 'Đã ra'),
('RFID_UED_102', '73K1-34211', '2026-04-19 07:45:00', '/storage/in/73K1-34211_3.jpg', '2026-04-19 10:45:00', '/storage/out/73K1-34211_3.jpg', 3000, 'Đã ra'),
('RFID_UED_103', '43C1-99800', '2026-04-19 08:00:00', '/storage/in/43C1-99800_4.jpg', '2026-04-19 12:00:00', '/storage/out/43C1-99800_4.jpg', 3000, 'Đã ra'),
('RFID_UED_104', '74F1-11123', '2026-04-19 08:15:00', '/storage/in/74F1-11123_5.jpg', '2026-04-19 13:15:00', '/storage/out/74F1-11123_5.jpg', 3000, 'Đã ra'),
('RFID_UED_105', '43D1-45678', '2026-04-19 08:30:00', '/storage/in/43D1-45678_6.jpg', '2026-04-19 11:30:00', '/storage/out/43D1-45678_6.jpg', 3000, 'Đã ra'),
('RFID_UED_105', '43D1-45679', '2026-04-19 08:45:00', '/storage/in/43D1-45679_7.jpg', '2026-04-19 13:45:00', '/storage/out/43D1-45679_7.jpg', 3000, 'Đã ra'),
('RFID_UED_106', '75G1-66788', '2026-04-19 09:00:00', '/storage/in/75G1-66788_8.jpg', '2026-04-19 10:00:00', '/storage/out/75G1-66788_8.jpg', 3000, 'Đã ra'),
('RFID_UED_107', '43E1-22344', '2026-04-19 09:15:00', '/storage/in/43E1-22344_9.jpg', '2026-04-19 13:15:00', '/storage/out/43E1-22344_9.jpg', 3000, 'Đã ra'),
('RFID_UED_108', '92N1-55433', '2026-04-19 09:30:00', '/storage/in/92N1-55433_10.jpg', NULL, NULL, 0, 'Đang đỗ'),
('RFID_UED_109', '73M1-88912', '2026-04-19 09:45:00', '/storage/in/73M1-88912_11.jpg', NULL, NULL, 0, 'Đang đỗ'),
('RFID_UED_110', '43F1-33455', '2026-04-19 10:00:00', '/storage/in/43F1-33455_12.jpg', NULL, NULL, 0, 'Đang đỗ'),
('RFID_UED_111', '74L1-77654', '2026-04-19 10:15:00', '/storage/in/74L1-77654_13.jpg', NULL, NULL, 0, 'Đang đỗ'),
('RFID_UED_112', '92K1-12399', '2026-04-19 10:30:00', '/storage/in/92K1-12399_14.jpg', NULL, NULL, 0, 'Đang đỗ'),
('RFID_UED_113', '43H1-11223', '2026-04-19 10:45:00', '/storage/in/43H1-11223_15.jpg', NULL, NULL, 0, 'Đang đỗ'),
('RFID_UED_114', '43H1-11224', '2026-04-19 11:00:00', '/storage/in/43H1-11224_16.jpg', NULL, NULL, 0, 'Đang đỗ'),
('RFID_UED_115', '43K1-20202', '2026-04-19 11:15:00', '/storage/in/43K1-20202_17.jpg', NULL, NULL, 0, 'Đang đỗ');
