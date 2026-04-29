# createbarcode - YOLOv8 API + Student QR + Product Barcode Scanner

This project includes:
- SQLite database with sample student data
- QR/REFC generation for all students
- Product-style barcode (EAN13) generation for all students
- YOLOv8 API endpoint for detection and target lock
- Laptop camera GUI scanner for QR and barcode (auto every 3 seconds, no key press)

## Project structure

- camera.py: main CLI entrypoint
- app/database.py: database schema, seed, queries
- app/qr_generator.py: generate student QR cards, barcode cards, and sheet images
- app/yolo_api.py: FastAPI + YOLOv8 detect endpoint
- app/gui_scanner.py: Tkinter GUI + webcam + auto scan
- data/students_seed.json: sample student records
- qr_codes/: output QR images

## Install

```bash
pip install -r requirements.txt
```

## Use custom YOLO model (optional)

If you have a trained model (example best.pt), set it before running API:

```bash
export YOLO_MODEL_PATH=/absolute/path/to/best.pt
```

If not set, API uses `yolov8n.pt`.

## Run

1) Setup database and choose code type to generate (menu 1: QR, 2: Barcode):

```bash
python camera.py setup --reset
```

If you run `camera.py all`, the app still auto-generates both QR and Barcode before starting API + GUI.

2) Start YOLOv8 API:

```bash
python camera.py api --host 127.0.0.1 --port 8000
```

3) Start GUI scanner in another terminal:

```bash
python camera.py gui --api-url http://127.0.0.1:8000/detect --detect-interval 3 --qr-interval 3
```

Or run all in one command:

```bash
python camera.py all
```

## How it works

- GUI draws a red center line as target aim line.
- Every 3 seconds, current camera frame is sent to YOLO API.
- API returns detections and the nearest target to center line.
- GUI overlays target box and continuously tries decoding QR and product barcode.
- For QR, payload can contain student_id/ref_code/product_code.
- For barcode (EAN13), GUI decodes product code via zxing-cpp and resolves student data from SQLite.
- On valid code, GUI displays student details in the info panel.

## Code outputs for testing

After setup, you get:
- One card per student in `qr_codes/`
- One product barcode card per student in `barcodes/`
- A combined sheet in `qr_codes/students_qr_sheet.png`
- A combined sheet in `barcodes/students_barcode_sheet.png`

You can show/print QR or barcode images and point laptop camera to test scanning.
