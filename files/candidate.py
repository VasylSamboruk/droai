from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import cv2
import numpy as np


@dataclass
class CandidateState:
    class_name: str
    box: list[float]
    last_seen: float
    category: str
    observations: int = 0
    checks: list[float] = field(default_factory=list)
    confirmed: bool = False


class CandidateManager:
    def __init__(
        self,
        min_confidence: float,
        max_candidate_confidence: float,
        confirmed_confidence: float,
        crop_confirm_confidence: float,
        max_candidates: int,
        check_every: int,
        confirm_checks: int,
        timeout: float,
        crop_size: int,
    ) -> None:
        self.min_confidence = min_confidence
        self.max_candidate_confidence = max_candidate_confidence
        self.confirmed_confidence = confirmed_confidence
        self.crop_confirm_confidence = crop_confirm_confidence
        self.max_candidates = max_candidates
        self.check_every = check_every
        self.confirm_checks = confirm_checks
        self.timeout = timeout
        self.crop_size = crop_size
        self._states: dict[str, CandidateState] = {}
        self.total_checks = 0

    def update(
        self,
        frame: np.ndarray,
        detections: list[dict[str, Any]],
        frame_index: int,
        check_crop: Callable[[np.ndarray, int], tuple[str, float] | None],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        now = time.monotonic()
        self._states = {
            key: state for key, state in self._states.items()
            if now - state.last_seen <= self.timeout
        }
        visible: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []

        for detection in detections:
            confidence = detection["confidence"]
            if confidence >= self.confirmed_confidence:
                visible.append(detection)
                continue
            if confidence < self.min_confidence:
                continue

            key = self._key(detection)
            if detection.get("track_id") is None:
                matched_key = self._match_existing(detection)
                if matched_key is not None:
                    key = matched_key
            state = self._states.get(key)
            if state is None:
                if sum(not item.confirmed for item in self._states.values()) >= self.max_candidates:
                    continue
                category = "weak" if confidence <= self.max_candidate_confidence else "suspicious"
                state = CandidateState(detection["class"], detection["box"], now, category)
                self._states[key] = state
            state.box = detection["box"]
            state.last_seen = now
            state.category = "weak" if confidence <= self.max_candidate_confidence else "suspicious"
            state.observations += 1
            if state.confirmed:
                visible.append(detection)
                continue

            if frame_index % self.check_every == 0:
                crop = self._crop(frame, state.box)
                if crop.size:
                    self.total_checks += 1
                    result = check_crop(crop, self.crop_size)
                    score = result[1] if result and result[0] == state.class_name else 0.0
                    state.checks.append(score)
                    state.checks = state.checks[-self.confirm_checks:]
                    if len(state.checks) == self.confirm_checks and state.observations >= self.confirm_checks:
                        if sum(state.checks) / len(state.checks) >= self.crop_confirm_confidence:
                            state.confirmed = True

            if state.confirmed:
                visible.append(detection)
            else:
                candidate = dict(detection)
                candidate["candidate_type"] = state.category
                candidates.append(candidate)

        return visible, candidates

    @staticmethod
    def _key(detection: dict[str, Any]) -> str:
        track_id = detection.get("track_id")
        if track_id is not None:
            return f"{detection['class']}:{track_id}"
        box = detection["box"]
        return f"{detection['class']}:{int(box[0] // 24)}:{int(box[1] // 24)}"

    def _match_existing(self, detection: dict[str, Any]) -> str | None:
        best_key = None
        best_overlap = 0.2
        for key, state in self._states.items():
            if state.class_name != detection["class"]:
                continue
            overlap = self._intersection_over_union(state.box, detection["box"])
            if overlap > best_overlap:
                best_key = key
                best_overlap = overlap
        return best_key

    @staticmethod
    def _intersection_over_union(first: list[float], second: list[float]) -> float:
        left = max(first[0], second[0])
        top = max(first[1], second[1])
        right = min(first[2], second[2])
        bottom = min(first[3], second[3])
        intersection = max(0.0, right - left) * max(0.0, bottom - top)
        first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
        second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
        union = first_area + second_area - intersection
        return intersection / union if union else 0.0

    def _crop(self, frame: np.ndarray, box: list[float]) -> np.ndarray:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = box
        padding_x = max(4, int((x2 - x1) * 0.2))
        padding_y = max(4, int((y2 - y1) * 0.2))
        left = max(0, int(x1) - padding_x)
        top = max(0, int(y1) - padding_y)
        right = min(width, int(x2) + padding_x)
        bottom = min(height, int(y2) + padding_y)
        crop = frame[top:bottom, left:right]
        if crop.size == 0:
            return crop
        return cv2.resize(crop, (self.crop_size, self.crop_size), interpolation=cv2.INTER_LINEAR)