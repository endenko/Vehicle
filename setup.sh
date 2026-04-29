#!/bin/bash
# SmartParking Valkyrie - Setup Script
# Chạy script này lần đầu để cấu hình dự án

set -e

echo "=================================================="
echo "SmartParking Valkyrie - Setup Script"
echo "=================================================="
echo ""

# 1. Kiểm tra Python
echo "[1/4] Kiểm tra Python..."
python --version

# 2. Cài đặt dependencies
echo ""
echo "[2/4] Cài đặt dependencies..."
pip install -r requirements.txt

# 3. Tạo .env từ .env.example
echo ""
echo "[3/4] Cấu hình environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Tạo .env (vui lòng điều chỉnh cấu hình database)"
else
    echo "✓ .env đã tồn tại"
fi

# 4. Tạo thư mục cần thiết
echo ""
echo "[4/4] Tạo thư mục lưu trữ..."
mkdir -p static/{in,out,tmp}
echo "✓ Thư mục lưu trữ sẵn sàng"

echo ""
echo "=================================================="
echo "✓ Setup hoàn thành!"
echo ""
echo "Bước tiếp theo:"
echo "1. Điều chỉnh cấu hình database trong .env"
echo "2. Tải Google Cloud Vision key.json"
echo "3. Chạy: python run.py all"
echo "=================================================="
