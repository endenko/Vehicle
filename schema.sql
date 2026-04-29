-- SmartParking Valkyrie Database Schema
-- SQL Server Script
-- Run này trước khi khởi động ứng dụng

-- ==========================================================
-- 1. TẠO DATABASE
-- ==========================================================
USE master;
GO

IF EXISTS (SELECT * FROM sys.databases WHERE name = 'SmartParking_Valkyrie')
BEGIN
    DROP DATABASE SmartParking_Valkyrie;
END
GO

CREATE DATABASE SmartParking_Valkyrie;
GO

USE SmartParking_Valkyrie;
GO

-- ==========================================================
-- 2. TẠO TABLES
-- ==========================================================

-- Sinh viên
CREATE TABLE SinhVien (
    MaSV NVARCHAR(50) PRIMARY KEY,
    HoTen NVARCHAR(100) NOT NULL,
    Khoa NVARCHAR(100),
    Lop NVARCHAR(50),
    SDT NVARCHAR(20),
    NgayTao DATETIME DEFAULT GETDATE()
);

-- Xe của sinh viên
CREATE TABLE Xe (
    BienSo NVARCHAR(50) PRIMARY KEY,
    MaSV NVARCHAR(50) NOT NULL FOREIGN KEY REFERENCES SinhVien(MaSV),
    LoaiXe NVARCHAR(100),
    MauSac NVARCHAR(50),
    TinhTrang NVARCHAR(20) DEFAULT N'Không Khóa',
    NgayTao DATETIME DEFAULT GETDATE()
);

-- Thẻ RFID (nếu dùng)
CREATE TABLE TheRFID (
    MaRFID NVARCHAR(50) PRIMARY KEY,
    MaSV NVARCHAR(50) NOT NULL FOREIGN KEY REFERENCES SinhVien(MaSV),
    SoDu INT DEFAULT 0,
    TinhTrang NVARCHAR(20) DEFAULT N'Hoạt động',
    NgayTao DATETIME DEFAULT GETDATE()
);

-- Lịch sử vào/ra
CREATE TABLE LichSuVaoRa (
    ID INT IDENTITY(1,1) PRIMARY KEY,
    MaRFID NVARCHAR(50) FOREIGN KEY REFERENCES TheRFID(MaRFID),
    BienSo NVARCHAR(50) FOREIGN KEY REFERENCES Xe(BienSo),
    ThoiGianVao DATETIME NOT NULL,
    AnhVao NVARCHAR(MAX),
    ThoiGianRa DATETIME,
    AnhRa NVARCHAR(MAX),
    SoTienTru INT DEFAULT 0,
    TrangThai NVARCHAR(50) DEFAULT N'Đang đỗ',
    NgayTao DATETIME DEFAULT GETDATE()
);

-- ==========================================================
-- 3. INDEXES (Tối ưu truy vấn)
-- ==========================================================
CREATE INDEX IX_Xe_MaSV ON Xe(MaSV);
CREATE INDEX IX_TheRFID_MaSV ON TheRFID(MaSV);
CREATE INDEX IX_LichSuVaoRa_BienSo ON LichSuVaoRa(BienSo);
CREATE INDEX IX_LichSuVaoRa_TrangThai ON LichSuVaoRa(TrangThai);
CREATE INDEX IX_LichSuVaoRa_ThoiGianVao ON LichSuVaoRa(ThoiGianVao);

-- ==========================================================
-- 4. CHÈN DỮ LIỆU MẪU DATA
-- ==========================================================

INSERT INTO SinhVien (MaSV, HoTen, Khoa, Lop, SDT) VALUES
(N'SV21001', N'Nguyễn Văn An', N'Sư phạm Tin', N'21SPT1', N'0901234501'),
(N'SV21002', N'Trần Thị Bích', N'Sư phạm Tin', N'21SPT1', N'0901234502'),
(N'SV21003', N'Lê Hoàng Cường', N'CNTT', N'21IT2', N'0901234503'),
(N'SV21004', N'Phạm Mỹ Dung', N'Sư phạm Tin', N'22SPT1', N'0901234504'),
(N'SV21005', N'Vũ Đức Anh', N'Sư phạm Lý', N'21SPL', N'0901234505'),
(N'SV21006', N'Đặng Thanh Hải', N'Sư phạm Tin', N'21SPT2', N'0901234506'),
(N'SV21007', N'Bùi Tấn Gia', N'CNTT', N'20IT3', N'0901234507'),
(N'SV21008', N'Hồ Xuân Hương', N'Sư phạm Ngữ Văn', N'22SPV', N'0901234508'),
(N'SV21009', N'Ngô Hữu Trí', N'Sư phạm Hóa', N'21SPH', N'0901234509'),
(N'SV21010', N'Đoàn Văn Trọng', N'Sư phạm Tin', N'21SPT1', N'0901234510'),
(N'SV21011', N'Lý Thảo My', N'Sư phạm Sinh', N'23SPS', N'0901234511'),
(N'SV21012', N'Châu Tấn Phát', N'CNTT', N'21IT1', N'0901234512'),
(N'SV21013', N'Đỗ Quyên Quyên', N'Sư phạm Lịch Sử', N'22SPLS', N'0901234513'),
(N'SV21014', N'Võ Minh Quân', N'Sư phạm Địa', N'21SPD', N'0901234514'),
(N'SV21015', N'Thái Tuấn Kiệt', N'Sư phạm Tin', N'21SPT2', N'0901234515'),
(N'SV21016', N'Phan Gia Bảo', N'CNTT', N'22IT1', N'0901234516'),
(N'SV21017', N'Nguyễn Thảo Linh', N'Kinh tế', N'22KT1', N'0901234517'),
(N'SV21018', N'Trần Đức Huy', N'CNTT', N'23IT1', N'0901234518'),
(N'SV21019', N'Võ Lan Phương', N'Ngoại ngữ', N'21NN1', N'0901234519'),
(N'SV21020', N'Lê Minh Khoa', N'CNTT', N'20IT1', N'0901234520');

INSERT INTO Xe (BienSo, MaSV, LoaiXe, MauSac, TinhTrang) VALUES
(N'43A1-12345', N'SV21001', N'Honda AirBlade', N'Đen', N'Không Khóa'),
(N'43B1-55522', N'SV21001', N'Yamaha Sirius', N'Đỏ', N'Khóa'),
(N'92H1-77899', N'SV21002', N'Honda Wave', N'Xanh', N'Không Khóa'),
(N'73K1-34211', N'SV21003', N'Yamaha Exciter', N'Trắng', N'Không Khóa'),
(N'43C1-99800', N'SV21004', N'Honda Vision', N'Trắng', N'Không Khóa'),
(N'74F1-11123', N'SV21005', N'Honda Winner X', N'Đen nhám', N'Không Khóa'),
(N'43D1-45678', N'SV21006', N'Yamaha Grande', N'Hồng', N'Không Khóa'),
(N'43D1-45679', N'SV21006', N'VinFast Feliz', N'Trắng', N'Không Khóa'),
(N'75G1-66788', N'SV21007', N'Honda Lead', N'Vàng', N'Không Khóa'),
(N'43E1-22344', N'SV21008', N'Vespa', N'Xám', N'Khóa'),
(N'92N1-55433', N'SV21009', N'Honda SH', N'Trắng', N'Không Khóa'),
(N'73M1-88912', N'SV21010', N'Yamaha NVX', N'Xanh GP', N'Không Khóa'),
(N'43F1-33455', N'SV21011', N'Honda Wave RSX', N'Đen', N'Không Khóa'),
(N'74L1-77654', N'SV21012', N'Suzuki Raider', N'Đen', N'Không Khóa'),
(N'92K1-12399', N'SV21013', N'Honda PCX', N'Xám', N'Không Khóa'),
(N'43G1-98765', N'SV21014', N'Yamaha Jupiter', N'Xanh', N'Không Khóa'),
(N'75H1-44566', N'SV21015', N'Honda Vario', N'Trắng', N'Không Khóa'),
(N'43A1-00001', N'SV21003', N'Honda Cub', N'Xanh nhạt', N'Không Khóa'),
(N'43H1-11223', N'SV21016', N'Honda Click', N'Đen', N'Không Khóa'),
(N'43H1-11224', N'SV21017', N'Yamaha Janus', N'Trắng', N'Không Khóa'),
(N'92P1-77881', N'SV21018', N'Honda Blade', N'Đỏ', N'Không Khóa'),
(N'75K1-90909', N'SV21019', N'Suzuki Address', N'Xanh', N'Không Khóa'),
(N'43K1-20202', N'SV21020', N'VinFast Evo', N'Đen', N'Không Khóa');

INSERT INTO TheRFID (MaRFID, MaSV, SoDu, TinhTrang) VALUES
(N'RFID_UED_100', N'SV21001', 94985, N'Hoạt động'),
(N'RFID_UED_101', N'SV21002', 174788, N'Hoạt động'),
(N'RFID_UED_102', N'SV21003', 160415, N'Hoạt động'),
(N'RFID_UED_103', N'SV21004', 71604, N'Hoạt động'),
(N'RFID_UED_104', N'SV21005', 13402, N'Hoạt động'),
(N'RFID_UED_105', N'SV21006', 132361, N'Hoạt động'),
(N'RFID_UED_106', N'SV21007', 0, N'Hoạt động'),
(N'RFID_UED_107', N'SV21008', 184672, N'Khóa'),
(N'RFID_UED_108', N'SV21009', 24406, N'Hoạt động'),
(N'RFID_UED_109', N'SV21010', 150891, N'Hoạt động'),
(N'RFID_UED_110', N'SV21011', 62384, N'Hoạt động'),
(N'RFID_UED_111', N'SV21012', 2000, N'Hoạt động'),
(N'RFID_UED_112', N'SV21013', 62364, N'Hoạt động'),
(N'RFID_UED_113', N'SV21016', 55000, N'Hoạt động'),
(N'RFID_UED_114', N'SV21017', 1000, N'Hoạt động'),
(N'RFID_UED_115', N'SV21020', 89000, N'Hoạt động');

INSERT INTO LichSuVaoRa (MaRFID, BienSo, ThoiGianVao, AnhVao, ThoiGianRa, AnhRa, SoTienTru, TrangThai) VALUES
(N'RFID_UED_100', N'43A1-12345', '2026-04-19 07:00:00', '/storage/in/43A1-12345_0.jpg', '2026-04-19 12:00:00', '/storage/out/43A1-12345_0.jpg', 3000, N'Đã ra'),
(N'RFID_UED_100', N'43B1-55522', '2026-04-19 07:15:00', '/storage/in/43B1-55522_1.jpg', '2026-04-19 12:15:00', '/storage/out/43B1-55522_1.jpg', 3000, N'Đã ra'),
(N'RFID_UED_101', N'92H1-77899', '2026-04-19 07:30:00', '/storage/in/92H1-77899_2.jpg', '2026-04-19 08:30:00', '/storage/out/92H1-77899_2.jpg', 3000, N'Đã ra'),
(N'RFID_UED_102', N'73K1-34211', '2026-04-19 07:45:00', '/storage/in/73K1-34211_3.jpg', '2026-04-19 10:45:00', '/storage/out/73K1-34211_3.jpg', 3000, N'Đã ra'),
(N'RFID_UED_103', N'43C1-99800', '2026-04-19 08:00:00', '/storage/in/43C1-99800_4.jpg', '2026-04-19 12:00:00', '/storage/out/43C1-99800_4.jpg', 3000, N'Đã ra'),
(N'RFID_UED_104', N'74F1-11123', '2026-04-19 08:15:00', '/storage/in/74F1-11123_5.jpg', '2026-04-19 13:15:00', '/storage/out/74F1-11123_5.jpg', 3000, N'Đã ra'),
(N'RFID_UED_105', N'43D1-45678', '2026-04-19 08:30:00', '/storage/in/43D1-45678_6.jpg', '2026-04-19 11:30:00', '/storage/out/43D1-45678_6.jpg', 3000, N'Đã ra'),
(N'RFID_UED_105', N'43D1-45679', '2026-04-19 08:45:00', '/storage/in/43D1-45679_7.jpg', '2026-04-19 13:45:00', '/storage/out/43D1-45679_7.jpg', 3000, N'Đã ra'),
(N'RFID_UED_106', N'75G1-66788', '2026-04-19 09:00:00', '/storage/in/75G1-66788_8.jpg', '2026-04-19 10:00:00', '/storage/out/75G1-66788_8.jpg', 3000, N'Đã ra'),
(N'RFID_UED_107', N'43E1-22344', '2026-04-19 09:15:00', '/storage/in/43E1-22344_9.jpg', '2026-04-19 13:15:00', '/storage/out/43E1-22344_9.jpg', 3000, N'Đã ra'),
(N'RFID_UED_108', N'92N1-55433', '2026-04-19 09:30:00', '/storage/in/92N1-55433_10.jpg', NULL, NULL, 0, N'Đang đỗ'),
(N'RFID_UED_109', N'73M1-88912', '2026-04-19 09:45:00', '/storage/in/73M1-88912_11.jpg', NULL, NULL, 0, N'Đang đỗ'),
(N'RFID_UED_110', N'43F1-33455', '2026-04-19 10:00:00', '/storage/in/43F1-33455_12.jpg', NULL, NULL, 0, N'Đang đỗ'),
(N'RFID_UED_111', N'74L1-77654', '2026-04-19 10:15:00', '/storage/in/74L1-77654_13.jpg', NULL, NULL, 0, N'Đang đỗ'),
(N'RFID_UED_112', N'92K1-12399', '2026-04-19 10:30:00', '/storage/in/92K1-12399_14.jpg', NULL, NULL, 0, N'Đang đỗ'),
(N'RFID_UED_113', N'43H1-11223', '2026-04-19 10:45:00', '/storage/in/43H1-11223_15.jpg', NULL, NULL, 0, N'Đang đỗ'),
(N'RFID_UED_114', N'43H1-11224', '2026-04-19 11:00:00', '/storage/in/43H1-11224_16.jpg', NULL, NULL, 0, N'Đang đỗ'),
(N'RFID_UED_115', N'43K1-20202', '2026-04-19 11:15:00', '/storage/in/43K1-20202_17.jpg', NULL, NULL, 0, N'Đang đỗ');

-- ==========================================================
-- 5. KIỂM TRA
-- ==========================================================
SELECT 'SinhVien' AS Bang, COUNT(*) AS Tong FROM SinhVien;
SELECT 'Xe' AS Bang, COUNT(*) AS Tong FROM Xe;
SELECT 'TheRFID' AS Bang, COUNT(*) AS Tong FROM TheRFID;
SELECT 'LichSuVaoRa' AS Bang, COUNT(*) AS Tong FROM LichSuVaoRa;
GO
