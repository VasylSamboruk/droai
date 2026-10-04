from __future__ import annotations

from typing import Any

import cv2
import numpy as np


class Overlay:
    def __init__(self, thickness: int = 2, smoothing: float = 0.7, show_fps: bool = True) -> None:
        self.thickness = thickness
        self.smoothing = smoothing
        self.show_fps = show_fps
        self._smoothed_boxes: dict[int, list[float]] = {}

    def reset(self) -> None:
        self._smoothed_boxes.clear()

    def draw(
        self,
        frame: np.ndarray,
        detections: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        stats: dict[str, Any],
        show_candidates: bool = False,
    ) -> np.ndarray:
        output = frame.copy()
        for detection in detections:
            self._draw_box(output, self._smooth(detection), (70, 205, 120), stats.get("show_id", True), stats.get("show_confidence", True))
        if show_candidates:
            for candidate in candidates:
                color = (30, 190, 245) if candidate.get("candidate_type") == "weak" else (80, 145, 240)
                self._draw_box(output, candidate, color, stats.get("show_id", True), stats.get("show_confidence", True))

        lines = [
            f"TARGETS {len(detections)}   CANDIDATES {len(candidates)}   ROI CHECKS {stats.get('candidate_checks', 0)}"
        ]
        if self.show_fps:
            lines[:0] = [f"VIDEO {stats.get('video_fps', 0):.1f} FPS", f"AI {stats.get('ai_fps', 0):.1f} FPS"]
        for row, text in enumerate(lines):
            y = 28 + row * 24
            cv2.putText(output, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(output, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (235, 242, 238), 1, cv2.LINE_AA)
        return output

    def _smooth(self, detection: dict[str, Any]) -> dict[str, Any]:
        track_id = detection.get("track_id")
        if track_id is None:
            return detection
        previous = self._smoothed_boxes.get(track_id)
        current = detection["box"]
        if previous is not None:
            current = [old * self.smoothing + new * (1 - self.smoothing) for old, new in zip(previous, current)]
        self._smoothed_boxes[track_id] = current
        smoothed = dict(detection)
        smoothed["box"] = current
        return smoothed

    def _draw_box(self, frame: np.ndarray, detection: dict[str, Any], color: tuple[int, int, int], show_id: bool, show_confidence: bool) -> None:
        x1, y1, x2, y2 = (int(value) for value in detection["box"])
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, self.thickness)
        parts = [detection["class"]]
        if detection.get("candidate_type"):
            parts.append(detection["candidate_type"].upper())
        if show_id and detection.get("track_id") is not None:
            parts.append(f"#{detection['track_id']}")
        if show_confidence:
            parts.append(f"{detection['confidence']:.2f}")
        label = "  ".join(parts)
        label_y = max(20, y1 - 8)
        cv2.putText(frame, label, (x1, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 2, cv2.LINE_AA)