from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from NEW.target_lock import TargetLock


class Overlay:
    def __init__(self, thickness: int = 2, smoothing: float = 0.7, show_fps: bool = True) -> None:
        self.thickness = thickness
        self.smoothing = smoothing
        self.show_fps = show_fps
        self._smoothed_boxes: dict[int, list[float]] = {}
        self._box_classes: dict[int, str] = {}
        self._box_last_seen: dict[int, int] = {}
        self._draw_index = 0

    def reset(self) -> None:
        self._smoothed_boxes.clear()
        self._box_classes.clear()
        self._box_last_seen.clear()
        self._draw_index = 0

    def draw(
        self,
        frame: np.ndarray,
        detections: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        stats: dict[str, Any],
        show_candidates: bool = False,
        minimal_hud: bool = False,
        target_lock: dict[str, Any] | None = None,
    ) -> np.ndarray:
        self._draw_index += 1
        self._claimed_boxes: set[int] = set()
        output = frame.copy()
        for detection in detections:
            if self._is_locked_detection(detection, target_lock):
                continue
            self._draw_box(
                output,
                self._smooth(detection),
                (70, 205, 120),
                stats.get("show_id", True) and not minimal_hud,
                stats.get("show_confidence", True) and not minimal_hud,
                not minimal_hud,
            )
        if show_candidates:
            for candidate in candidates:
                color = (30, 190, 245) if candidate.get("candidate_type") == "weak" else (80, 145, 240)
                self._draw_box(
                    output,
                    candidate,
                    color,
                    stats.get("show_id", True) and not minimal_hud,
                    stats.get("show_confidence", True) and not minimal_hud,
                    not minimal_hud,
                )

        if target_lock is not None:
            TargetLock.draw_locked_overlay(output, frame, target_lock, self.thickness)

        if minimal_hud:
            lock_status = stats.get("target_lock_status", {})
            if not lock_status.get("enabled", True):
                lock_label = "LOCK OFF"
            elif target_lock is not None:
                lock_label = f"LOCK #{target_lock['track_id']}" if target_lock.get("track_id") is not None else "LOCK ON"
            else:
                lock_label = "LOCK READY"
            lines = [f"FPS {stats.get('video_fps', 0):.0f}   MATCHES {len(detections)}   {lock_label}"]
            approach = stats.get("approach") or {}
            if approach.get("range_m") is not None:
                tx_state = str((stats.get("approach_tx") or {}).get("state") or "")
                tx_label = f"  TX {tx_state.upper()}" if tx_state and tx_state != "idle" else ""
                lines.append(
                    f"RNG {approach['range_m']:.1f}m  VX {approach['forward_m_s']:+.2f}  {str(approach.get('state', '')).upper()}{tx_label}"
                )
                tx = stats.get("approach_tx") or {}
                if tx.get("roll_pwm") is not None:
                    lines.append(
                        f"ACRO R{tx['roll_pwm']} P{tx['pitch_pwm']} Y{tx['yaw_pwm']} T{tx['throttle_pwm']}"
                    )
                acro = tx.get("acro") or {}
                if acro.get("pitch_compensation_active"):
                    view_state = "IN VIEW" if acro.get("target_in_view") else "OUT OF VIEW"
                    lines.append(f"PITCH COMP {view_state}")
        else:
            lines = [
                f"TARGETS {len(detections)}   CANDIDATES {len(candidates)}   ROI CHECKS {stats.get('candidate_checks', 0)}"
            ]
            if self.show_fps:
                lines[:0] = [f"VIDEO {stats.get('video_fps', 0):.1f} FPS", f"AI {stats.get('ai_fps', 0):.1f} FPS"]
            approach = stats.get("approach") or {}
            if approach.get("range_m") is not None:
                tx_state = str((stats.get("approach_tx") or {}).get("state") or "")
                tx_label = f"  TX {tx_state.upper()}" if tx_state and tx_state != "idle" else ""
                lines.append(
                    f"RNG {approach['range_m']:.1f}m  VX {approach['forward_m_s']:+.2f}  {str(approach.get('state', '')).upper()}{tx_label}"
                )
                tx = stats.get("approach_tx") or {}
                if tx.get("roll_pwm") is not None:
                    lines.append(
                        f"ACRO R{tx['roll_pwm']} P{tx['pitch_pwm']} Y{tx['yaw_pwm']} T{tx['throttle_pwm']}"
                    )
                acro = tx.get("acro") or {}
                if acro.get("pitch_compensation_active"):
                    view_state = "IN VIEW" if acro.get("target_in_view") else "OUT OF VIEW"
                    lines.append(f"PITCH COMP {view_state}")
        for row, text in enumerate(lines):
            y = 28 + row * 24
            cv2.putText(output, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(output, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (235, 242, 238), 1, cv2.LINE_AA)
        if target_lock is None and minimal_hud and detections:
            inset_target = max(detections, key=lambda item: item["confidence"])
            TargetLock.draw_inset(output, inset_target, source_frame=frame)
        return output

    @classmethod
    def _is_locked_detection(
        cls,
        detection: dict[str, Any],
        target_lock: dict[str, Any] | None,
    ) -> bool:
        if target_lock is None:
            return False
        locked_id = target_lock.get("track_id")
        if locked_id is not None and detection.get("track_id") == locked_id:
            return True
        return cls._intersection_over_union(detection["box"], target_lock["box"]) >= 0.65

    def _smooth(self, detection: dict[str, Any]) -> dict[str, Any]:
        track_id = detection.get("track_id")
        if track_id is None:
            return detection
        previous_id = track_id if track_id in self._smoothed_boxes else None
        if previous_id is not None and previous_id in self._claimed_boxes:
            previous_id = None
        if previous_id is None:
            previous_id = self._match_previous_box(detection)
        previous = self._smoothed_boxes.get(previous_id) if previous_id is not None else None
        current = detection["box"]
        if previous is not None:
            current = [old * self.smoothing + new * (1 - self.smoothing) for old, new in zip(previous, current)]
        if previous_id is not None and previous_id != track_id:
            self._smoothed_boxes.pop(previous_id, None)
            self._box_classes.pop(previous_id, None)
            self._box_last_seen.pop(previous_id, None)
        self._smoothed_boxes[track_id] = current
        self._box_classes[track_id] = detection["class"]
        self._box_last_seen[track_id] = self._draw_index
        self._claimed_boxes.add(track_id)
        expired = [
            key for key, last_seen in self._box_last_seen.items()
            if self._draw_index - last_seen > 2
        ]
        for key in expired:
            self._smoothed_boxes.pop(key, None)
            self._box_classes.pop(key, None)
            self._box_last_seen.pop(key, None)
        smoothed = dict(detection)
        smoothed["box"] = current
        return smoothed

    def _match_previous_box(self, detection: dict[str, Any]) -> int | None:
        current = detection["box"]
        center_x = (current[0] + current[2]) / 2
        center_y = (current[1] + current[3]) / 2
        diagonal = ((current[2] - current[0]) ** 2 + (current[3] - current[1]) ** 2) ** 0.5
        best_id = None
        best_score = float("-inf")
        for track_id, previous in self._smoothed_boxes.items():
            if (
                track_id in self._claimed_boxes
                or self._box_classes.get(track_id) != detection["class"]
                or self._draw_index - self._box_last_seen.get(track_id, 0) > 2
            ):
                continue
            previous_center_x = (previous[0] + previous[2]) / 2
            previous_center_y = (previous[1] + previous[3]) / 2
            distance = ((center_x - previous_center_x) ** 2 + (center_y - previous_center_y) ** 2) ** 0.5
            overlap = self._intersection_over_union(previous, current)
            max_distance = max(24.0, diagonal * 0.75)
            if overlap < 0.1 and distance > max_distance:
                continue
            score = overlap - distance / max_distance
            if score > best_score:
                best_id = track_id
                best_score = score
        return best_id

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

    def _draw_box(
        self,
        frame: np.ndarray,
        detection: dict[str, Any],
        color: tuple[int, int, int],
        show_id: bool,
        show_confidence: bool,
        show_label: bool = True,
    ) -> None:
        x1, y1, x2, y2 = (int(value) for value in detection["box"])
        t = self.thickness
        # тонка рамка + товсті кутики
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1, cv2.LINE_AA)
        c = max(8, min(x2 - x1, y2 - y1) // 4)
        for px, py, dx, dy in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
            cv2.line(frame, (px, py), (px + dx * c, py), color, t + 1, cv2.LINE_AA)
            cv2.line(frame, (px, py), (px, py + dy * c), color, t + 1, cv2.LINE_AA)
        parts = [detection["class"]]
        if detection.get("candidate_type"):
            parts.append(detection["candidate_type"].upper())
        if show_id and detection.get("track_id") is not None:
            parts.append(f"#{detection['track_id']}")
        if show_confidence:
            parts.append(f"{detection['confidence']:.2f}")
        if not show_label and detection.get("track_id") is None:
            return
        label = " ".join(parts) if show_label else f"#{detection['track_id']}"
        (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        ly = y1 - 4 if y1 - th - base - 6 > 0 else y1 + th + base + 4
        cv2.rectangle(frame, (x1, ly - th - base - 2), (x1 + tw + 8, ly + 2), color, -1)
        cv2.putText(frame, label, (x1 + 4, ly - base + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
