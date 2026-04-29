from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from ultralytics import YOLO

MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "yolov8n.pt")
DEFAULT_CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", "0.35"))
DEFAULT_MAX_DETECTIONS = int(os.getenv("YOLO_MAX_DETECTIONS", "20"))

try:
    YOLO_MODEL: Optional[YOLO] = YOLO(MODEL_PATH)
    MODEL_ERROR = ""
except Exception as model_error:
    YOLO_MODEL = None
    MODEL_ERROR = str(model_error)

app = FastAPI(title="YOLOv8 Target API", version="1.0.0")


def _decode_frame(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Invalid image data")
    return frame


def _to_detection_dict(result: Any, frame_width: int) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    detections: List[Dict[str, Any]] = []
    target: Optional[Dict[str, Any]] = None

    if result.boxes is None or len(result.boxes) == 0:
        return detections, target

    center_x = frame_width / 2.0
    nearest_distance = float("inf")

    for box in result.boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        conf = float(box.conf[0].item())
        class_id = int(box.cls[0].item())
        class_name = str(result.names.get(class_id, class_id))
        box_center_x = (x1 + x2) / 2.0
        distance_to_line = abs(box_center_x - center_x)

        detection = {
            "x1": int(x1),
            "y1": int(y1),
            "x2": int(x2),
            "y2": int(y2),
            "confidence": round(conf, 4),
            "class_id": class_id,
            "class_name": class_name,
            "distance_to_aim_line": round(distance_to_line, 2),
        }
        detections.append(detection)

        if distance_to_line < nearest_distance:
            nearest_distance = distance_to_line
            target = detection

    return detections, target


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok" if YOLO_MODEL is not None else "error",
        "model_path": MODEL_PATH,
        "model_ready": YOLO_MODEL is not None,
        "model_error": MODEL_ERROR,
    }


@app.post("/detect")
async def detect(
    file: UploadFile = File(...),
    conf: float = DEFAULT_CONFIDENCE,
    max_det: int = DEFAULT_MAX_DETECTIONS,
) -> Dict[str, Any]:
    if YOLO_MODEL is None:
        raise HTTPException(status_code=500, detail=f"YOLO model is not ready: {MODEL_ERROR}")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file")

    try:
        frame = _decode_frame(image_bytes)
    except ValueError as decode_error:
        raise HTTPException(status_code=400, detail=str(decode_error)) from decode_error

    height, width = frame.shape[:2]

    try:
        prediction = YOLO_MODEL.predict(
            source=frame,
            conf=max(0.01, min(conf, 0.99)),
            max_det=max(1, max_det),
            verbose=False,
        )[0]
    except Exception as infer_error:
        raise HTTPException(status_code=500, detail=f"YOLO inference failed: {infer_error}") from infer_error

    detections, target = _to_detection_dict(prediction, frame_width=width)

    return {
        "status": "ok",
        "width": width,
        "height": height,
        "aim_line": {
            "x1": width // 2,
            "y1": 0,
            "x2": width // 2,
            "y2": height,
            "color_bgr": [0, 0, 255],
        },
        "detections": detections,
        "target": target,
    }
