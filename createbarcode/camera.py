from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from typing import Any, Dict, Optional

from app.database import bootstrap_database
from app.qr_generator import generate_all_barcodes, generate_all_qr


def _print_generation_result(code_label: str, generation_result: Dict[str, Any]) -> None:
	print(f"{code_label} generated: {generation_result['total_students']} files")
	sheet_file = generation_result.get("sheet_file")
	if sheet_file:
		print(f"{code_label} sheet: {sheet_file}")


def _ask_setup_mode() -> str:
	print("\n=== Setup Menu ===")
	print("1. QR")
	print("2. Barcode")

	choice_map = {
		"1": "qr",
		"2": "barcode",
		"qr": "qr",
		"barcode": "barcode",
	}

	while True:
		choice = input("Chon 1/2 (hoac qr/barcode): ").strip().lower()
		if choice in choice_map:
			return choice_map[choice]
		print("Lua chon khong hop le. Vui long chon lai.")


def command_setup(reset: bool, setup_mode: Optional[str] = None) -> None:
	seeded_rows = bootstrap_database(reset=reset)
	print(f"Database ready. Seeded rows: {seeded_rows}")

	selected_mode = (setup_mode or _ask_setup_mode()).strip().lower()

	if selected_mode == "qr":
		qr_result = generate_all_qr()
		_print_generation_result("QR", qr_result)
		return

	if selected_mode == "barcode":
		barcode_result = generate_all_barcodes()
		_print_generation_result("Barcode", barcode_result)
		return

	if selected_mode == "all":
		qr_result = generate_all_qr()
		barcode_result = generate_all_barcodes()
		_print_generation_result("QR", qr_result)
		_print_generation_result("Barcode", barcode_result)
		return

	raise ValueError(f"Unsupported setup mode: {selected_mode}")


def command_api(host: str, port: int) -> None:
	uvicorn = importlib.import_module("uvicorn")
	uvicorn.run("app.yolo_api:app", host=host, port=port, reload=False)


def command_gui(api_url: str, detect_interval: float, qr_interval: float, camera_index: int) -> None:
	from app.gui_scanner import run_gui

	run_gui(
		api_url=api_url,
		detect_interval_seconds=detect_interval,
		qr_interval_seconds=qr_interval,
		camera_index=camera_index,
	)


def command_all(host: str, port: int, detect_interval: float, qr_interval: float, camera_index: int) -> None:
	api_url = f"http://{host}:{port}/detect"
	api_command = [
		sys.executable,
		"-m",
		"uvicorn",
		"app.yolo_api:app",
		"--host",
		host,
		"--port",
		str(port),
	]
	api_process = subprocess.Popen(api_command)

	try:
		print(f"YOLO API running at http://{host}:{port}")
		print("Starting GUI scanner...")
		command_gui(
			api_url=api_url,
			detect_interval=detect_interval,
			qr_interval=qr_interval,
			camera_index=camera_index,
		)
	finally:
		api_process.terminate()
		try:
			api_process.wait(timeout=5)
		except subprocess.TimeoutExpired:
			api_process.kill()


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="YOLOv8 API + Student QR/Product barcode scanner toolkit",
	)
	subparsers = parser.add_subparsers(dest="command", required=True)

	setup_parser = subparsers.add_parser("setup", help="Create DB and generate QR + barcode cards")
	setup_parser.add_argument("--reset", action="store_true", help="Recreate database from scratch")

	api_parser = subparsers.add_parser("api", help="Run YOLOv8 API server")
	api_parser.add_argument("--host", default="127.0.0.1")
	api_parser.add_argument("--port", default=8000, type=int)

	gui_parser = subparsers.add_parser("gui", help="Run scanner GUI")
	gui_parser.add_argument("--api-url", default="http://127.0.0.1:8000/detect")
	gui_parser.add_argument("--detect-interval", default=3.0, type=float)
	gui_parser.add_argument("--qr-interval", default=3.0, type=float)
	gui_parser.add_argument("--camera-index", default=0, type=int)

	all_parser = subparsers.add_parser("all", help="Run API and GUI together")
	all_parser.add_argument("--host", default="127.0.0.1")
	all_parser.add_argument("--port", default=8000, type=int)
	all_parser.add_argument("--detect-interval", default=3.0, type=float)
	all_parser.add_argument("--qr-interval", default=3.0, type=float)
	all_parser.add_argument("--camera-index", default=0, type=int)

	return parser


def main() -> None:
	parser = build_parser()
	args = parser.parse_args()

	if args.command == "setup":
		command_setup(reset=args.reset)
	elif args.command == "api":
		command_api(host=args.host, port=args.port)
	elif args.command == "gui":
		command_gui(
			api_url=args.api_url,
			detect_interval=args.detect_interval,
			qr_interval=args.qr_interval,
			camera_index=args.camera_index,
		)
	elif args.command == "all":
		command_setup(reset=False, setup_mode="all")
		command_all(
			host=args.host,
			port=args.port,
			detect_interval=args.detect_interval,
			qr_interval=args.qr_interval,
			camera_index=args.camera_index,
		)
	else:
		parser.print_help()


if __name__ == "__main__":
	main()
