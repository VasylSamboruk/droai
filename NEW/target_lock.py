from __future__ import annotations

from typing import Any

import cv2
import numpy as np


class TargetLock:
    INSET_SIZE = (240, 150)
    INSET_MARGIN = 12

    def __init__(self, flow_scale: float = 0.5) -> None:
        self.enabled = True
        self._flow_scale = min(1.0, max(0.25, float(flow_scale)))
        self._target: dict[str, Any] | None = None
        self._box: list[float] | None = None
        self._previous_gray: np.ndarray | None = None
        self._points: np.ndarray | None = None
        self._last_detection_version = -1
        self._needs_initialization = False
        self._lost_frames = 0

    @property
    def locked(self) -> bool:
        return self._target is not None

    def toggle(self, detections: list[dict[str, Any]]) -> bool:
        if self.locked:
            self.clear()
            return False
        if not self.enabled or not detections:
            return False

        target = max(detections, key=lambda item: float(item.get("confidence", 0.0)))
        self._set_target(target)
        return True

    def cycle(self, detections: list[dict[str, Any]]) -> bool:
        if not self.enabled or not self.locked:
            return False

        tracked = sorted(
            (item for item in detections if item.get("track_id") is not None),
            key=lambda item: int(item["track_id"]),
        )
        if len(tracked) < 2:
            return False

        current_id = self._target.get("track_id") if self._target else None
        current_index = next(
            (index for index, item in enumerate(tracked) if item["track_id"] == current_id),
            -1,
        )
        self._set_target(tracked[(current_index + 1) % len(tracked)])
        return True

    def _set_target(self, target: dict[str, Any]) -> None:
        self._target = dict(target)
        self._box = [float(value) for value in target["box"]]
        self._points = None
        self._previous_gray = None
        self._needs_initialization = True
        self._lost_frames = 0

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.clear()

    def clear(self) -> None:
        self._target = None
        self._box = None
        self._points = None
        self._previous_gray = None
        self._needs_initialization = False
        self._lost_frames = 0
        self._last_detection_version = -1

    def update(
        self,
        frame: np.ndarray,
        detections: list[dict[str, Any]],
        detection_version: int,
    ) -> dict[str, Any] | None:
        if not self.enabled or self._target is None or self._box is None:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._flow_scale < 1.0:
            gray = cv2.resize(
                gray,
                None,
                fx=self._flow_scale,
                fy=self._flow_scale,
                interpolation=cv2.INTER_AREA,
            )
        if self._needs_initialization:
            self._refresh_points(gray)
            self._needs_initialization = False
        else:
            flow_succeeded = self._follow_flow(gray)
            if detection_version != self._last_detection_version:
                matched = self._find_matching_detection(detections)
                if matched is not None:
                    previous_track_id = self._target.get("track_id")
                    self._target.update(
                        {key: matched[key] for key in ("class", "confidence") if key in matched}
                    )
                    if "track_id" in matched:
                        self._target["track_id"] = matched["track_id"]
                    if (
                        not flow_succeeded
                        or matched.get("track_id") != previous_track_id
                        or self._box_outside_frame(self._box, frame.shape)
                    ):
                        self._box = [float(value) for value in matched["box"]]
                        self._refresh_points(gray)
                self._last_detection_version = detection_version

        self._previous_gray = gray
        if self._box is None or self._box_outside_frame(self._box, frame.shape):
            self.clear()
            return None
        return {**self._target, "box": list(self._box)}

    @staticmethod
    def _box_outside_frame(box: list[float], frame_shape: tuple[int, ...]) -> bool:
        height, width = frame_shape[:2]
        left, top, right, bottom = box
        return right <= 0 or bottom <= 0 or left >= width or top >= height

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "locked": self.locked,
            "track_id": self._target.get("track_id") if self._target else None,
            "box": list(self._box) if self._box is not None else None,
        }

    @classmethod
    def draw_locked_overlay(
        cls,
        frame: np.ndarray,
        source_frame: np.ndarray,
        target: dict[str, Any],
        thickness: int = 2,
    ) -> None:
        height, width = frame.shape[:2]
        left, top, right, bottom = cls._inset_bounds(width, height)
        if left is not None:
            cls._draw_connector(frame, target["box"], (left, top, right, bottom))

        x1, y1, x2, y2 = (int(value) for value in target["box"])
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), thickness)
        label = "LOCK"
        if target.get("track_id") is not None:
            label += f" #{target['track_id']}"
        cv2.putText(
            frame,
            label,
            (max(8, x1), max(22, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        cls.draw_inset(frame, target, source_frame, locked=True)

    @classmethod
    def draw_inset(
        cls,
        frame: np.ndarray,
        detection: dict[str, Any],
        source_frame: np.ndarray | None = None,
        locked: bool = False,
    ) -> None:
        frame_height, frame_width = frame.shape[:2]
        box_width, box_height = cls.INSET_SIZE
        inset_bounds = cls._inset_bounds(frame_width, frame_height)
        if inset_bounds[0] is None:
            return

        source = frame if source_frame is None else source_frame
        x1, y1, x2, y2 = (float(value) for value in detection["box"])
        padding_x = max(8, (x2 - x1) * 0.25)
        padding_y = max(8, (y2 - y1) * 0.25)
        crop_x1 = max(0, min(frame_width, int(x1 - padding_x)))
        crop_y1 = max(0, min(frame_height, int(y1 - padding_y)))
        crop_x2 = max(0, min(frame_width, int(x2 + padding_x)))
        crop_y2 = max(0, min(frame_height, int(y2 + padding_y)))
        if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
            return

        inset_x, inset_y, _, _ = inset_bounds
        inset = cv2.resize(
            source[crop_y1:crop_y2, crop_x1:crop_x2],
            (box_width, box_height),
            interpolation=cv2.INTER_LINEAR,
        )
        frame[inset_y : inset_y + box_height, inset_x : inset_x + box_width] = inset
        cv2.rectangle(
            frame,
            (inset_x, inset_y),
            (inset_x + box_width, inset_y + box_height),
            (40, 225, 255),
            2,
        )
        target_id = detection.get("track_id")
        identity = f" #{target_id}" if target_id is not None else ""
        label = f"{'LOCK' if locked else 'TOP'}{identity} {detection['confidence']:.2f}"
        label_y = inset_y + box_height + 20
        cv2.rectangle(
            frame,
            (inset_x, label_y - 17),
            (inset_x + box_width, label_y + 4),
            (12, 18, 17),
            -1,
        )
        cv2.putText(
            frame,
            label,
            (inset_x + 6, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (235, 242, 238),
            1,
            cv2.LINE_AA,
        )

    @classmethod
    def _inset_bounds(
        cls,
        frame_width: int,
        frame_height: int,
    ) -> tuple[int | None, int, int, int]:
        box_width, box_height = cls.INSET_SIZE
        if frame_width < box_width + cls.INSET_MARGIN * 2 or frame_height < box_height + cls.INSET_MARGIN * 2:
            return None, 0, 0, 0
        left = frame_width - box_width - cls.INSET_MARGIN
        top = cls.INSET_MARGIN
        return left, top, left + box_width, top + box_height

    @staticmethod
    def _draw_connector(
        frame: np.ndarray,
        target_box: list[float],
        inset_box: tuple[int, int, int, int],
    ) -> None:
        x1, y1, x2, y2 = (int(value) for value in target_box)
        inset_left, inset_top, inset_right, inset_bottom = inset_box
        if x1 < inset_right and x2 > inset_left and y1 < inset_bottom and y2 > inset_top:
            return

        inset_center_x = (inset_left + inset_right) // 2
        inset_center_y = (inset_top + inset_bottom) // 2
        target_center_x = (x1 + x2) // 2
        target_center_y = (y1 + y2) // 2
        target_point = (
            min(max(inset_center_x, x1), x2),
            min(max(inset_center_y, y1), y2),
        )
        inset_point = (
            min(max(target_center_x, inset_left), inset_right),
            min(max(target_center_y, inset_top), inset_bottom),
        )
        cv2.line(frame, target_point, inset_point, (12, 18, 17), 5, cv2.LINE_AA)
        cv2.line(frame, target_point, inset_point, (0, 0, 255), 2, cv2.LINE_AA)

    def _find_matching_detection(
        self,
        detections: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if self._target is None:
            return None
        target_id = self._target.get("track_id")
        if target_id is not None:
            exact_match = next(
                (item for item in detections if item.get("track_id") == target_id),
                None,
            )
            if exact_match is not None:
                return exact_match

        same_class = [
            item for item in detections if item.get("class") == self._target.get("class")
        ]
        if not same_class or self._box is None:
            return None
        target_center = self._center(self._box)
        target_width = max(1.0, self._box[2] - self._box[0])
        target_height = max(1.0, self._box[3] - self._box[1])
        max_distance = max(48.0, float(np.hypot(target_width, target_height)) * 1.5)
        max_distance += min(self._lost_frames * 3.0, 240.0)
        nearby = [
            item for item in same_class
            if self._distance(target_center, item["box"]) <= max_distance
            or self._intersection_over_union(self._box, item["box"]) >= 0.05
        ]
        if not nearby:
            return None
        return min(nearby, key=lambda item: self._distance(target_center, item["box"]))

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

    def _follow_flow(self, gray: np.ndarray) -> bool:
        if self._previous_gray is None or self._points is None or len(self._points) < 3:
            self._lost_frames += 1
            return False

        next_points, status, _ = cv2.calcOpticalFlowPyrLK(
            self._previous_gray,
            gray,
            self._points,
            None,
            winSize=(21, 21),
            maxLevel=3,
        )
        if next_points is None or status is None:
            self._points = None
            self._lost_frames += 1
            return False

        good = status.reshape(-1) == 1
        old_points = self._points.reshape(-1, 2)[good]
        new_points = next_points.reshape(-1, 2)[good]
        if len(new_points) < 3:
            self._points = new_points.reshape(-1, 1, 2)
            self._lost_frames += 1
            return False

        displacement = np.median(new_points - old_points, axis=0)
        self._box = [
            self._box[0] + float(displacement[0]) / self._flow_scale,
            self._box[1] + float(displacement[1]) / self._flow_scale,
            self._box[2] + float(displacement[0]) / self._flow_scale,
            self._box[3] + float(displacement[1]) / self._flow_scale,
        ]
        self._points = new_points.reshape(-1, 1, 2)
        self._lost_frames = 0
        if len(new_points) < 8:
            self._refresh_points(gray)
        return True

    def _refresh_points(self, gray: np.ndarray) -> None:
        if self._box is None:
            self._points = None
            return
        height, width = gray.shape
        left, top, right, bottom = self._box
        left *= self._flow_scale
        top *= self._flow_scale
        right *= self._flow_scale
        bottom *= self._flow_scale
        box_width = max(1.0, right - left)
        box_height = max(1.0, bottom - top)
        margin_x = box_width * 0.12
        margin_y = box_height * 0.12
        x1 = max(0, min(width, int(left + margin_x)))
        y1 = max(0, min(height, int(top + margin_y)))
        x2 = max(x1, min(width, int(right - margin_x)))
        y2 = max(y1, min(height, int(bottom - margin_y)))
        if x2 - x1 < 3 or y2 - y1 < 3:
            self._points = None
            return

        mask = np.zeros_like(gray)
        mask[y1:y2, x1:x2] = 255
        self._points = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=80,
            qualityLevel=0.01,
            minDistance=4,
            mask=mask,
            blockSize=5,
        )

    @staticmethod
    def _center(box: list[float]) -> tuple[float, float]:
        return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2

    @classmethod
    def _distance(cls, center: tuple[float, float], box: list[float]) -> float:
        candidate_center = cls._center(box)
        return float(np.hypot(center[0] - candidate_center[0], center[1] - candidate_center[1]))
