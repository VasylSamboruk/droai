from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil


class DetectionEventLogger:
    def __init__(self, log_directory: Path) -> None:
        log_directory.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(f"drone_ai.events.{log_directory.resolve()}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        if not self._logger.handlers:
            handler = RotatingFileHandler(
                log_directory / "detections.jsonl",
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)
        self._process = psutil.Process()

    def log_inference(
        self,
        frame_index: int,
        detections: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        inference_ms: float,
        ai_fps: float,
        model: str,
    ) -> None:
        self._write({
            "event": "inference",
            "frame": frame_index,
            "model": model,
            "inference_ms": round(inference_ms, 2),
            "ai_fps": round(ai_fps, 2),
            "detections": [self._serialize_detection(item) for item in detections],
            "candidates": [self._serialize_detection(item) for item in candidates],
        })

    def log_error(self, message: str, frame_index: int) -> None:
        self._write({"event": "inference_error", "frame": frame_index, "message": message})

    def _write(self, event: dict[str, Any]) -> None:
        memory = psutil.virtual_memory()
        event.update({
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "system_cpu_percent": psutil.cpu_percent(interval=None),
            "process_cpu_percent": self._process.cpu_percent(interval=None),
            "process_rss_mb": round(self._process.memory_info().rss / (1024 * 1024), 2),
            "system_memory_percent": memory.percent,
            "system_memory_available_mb": round(memory.available / (1024 * 1024), 2),
        })
        self._logger.info(json.dumps(event, ensure_ascii=False, separators=(",", ":")))

    @staticmethod
    def _serialize_detection(detection: dict[str, Any]) -> dict[str, Any]:
        return {
            "class": detection["class"],
            "confidence": round(float(detection["confidence"]), 4),
            "track_id": detection.get("track_id"),
            "box": [round(float(value), 1) for value in detection["box"]],
            "candidate_type": detection.get("candidate_type"),
        }
