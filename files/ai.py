from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


class YOLODetector:
    def __init__(self, model_path: str | Path, image_size: int, target_classes: list[str]) -> None:
        from ultralytics import YOLO

        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        self.model: Any = YOLO(str(model_path))
        self._crop_model: Any | None = None
        self._model_path = str(model_path)
        self.image_size = image_size
        names = self.model.names
        self.class_names = {int(key): str(value) for key, value in names.items()} if isinstance(names, dict) else dict(enumerate(names))
        target_names = {name.casefold() for name in target_classes}
        self.class_ids = [class_id for class_id, name in self.class_names.items() if name.casefold() in target_names]
        if not self.class_ids:
            raise ValueError(f"Model has none of the configured target classes: {', '.join(target_classes)}")

    def check_crop(self, crop: np.ndarray, image_size: int) -> tuple[str, float] | None:
        if self._crop_model is None:
            from ultralytics import YOLO

            self._crop_model = YOLO(self._model_path)

        results = self._crop_model.predict(
            crop,
            conf=0.01,
            imgsz=image_size,
            classes=self.class_ids,
            verbose=False,
        )
        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            return None

        boxes = results[0].boxes
        best_index = int(boxes.conf.argmax().item())
        class_id = int(boxes.cls[best_index].item())
        confidence = float(boxes.conf[best_index].item())
        return self.class_names[class_id], confidence