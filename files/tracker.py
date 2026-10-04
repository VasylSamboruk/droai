from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import yaml


class BoTSORTTracker:
    def __init__(self, detector: Any, confidence: float, image_size: int, project_root: Path, settings: dict[str, Any]) -> None:
        self.detector = detector
        self.confidence = confidence
        self.image_size = image_size
        with (project_root / "files" / "botsort.yaml").open(encoding="utf-8") as tracker_file:
            tracker_settings = yaml.safe_load(tracker_file)
        tracker_settings.update(settings)
        self.tracker_config = project_root / "output" / "botsort_runtime.yaml"
        self.tracker_config.parent.mkdir(parents=True, exist_ok=True)
        with self.tracker_config.open("w", encoding="utf-8") as tracker_file:
            yaml.safe_dump(tracker_settings, tracker_file, sort_keys=False)

    def update(self, frame: np.ndarray) -> list[dict[str, Any]]:
        results = self.detector.model.track(
            frame,
            persist=True,
            tracker=str(self.tracker_config),
            conf=self.confidence,
            imgsz=self.image_size,
            classes=self.detector.class_ids,
            verbose=False,
        )
        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            return []

        boxes = results[0].boxes
        coordinates = boxes.xyxy.cpu().tolist()
        confidences = boxes.conf.cpu().tolist()
        class_ids = boxes.cls.cpu().tolist()
        track_ids = boxes.id.int().cpu().tolist() if boxes.id is not None else [None] * len(coordinates)

        return [
            {
                "class": self.detector.class_names[int(class_id)],
                "confidence": float(confidence),
                "box": [float(value) for value in box],
                "track_id": track_id,
            }
            for box, confidence, class_id, track_id in zip(coordinates, confidences, class_ids, track_ids)
        ]