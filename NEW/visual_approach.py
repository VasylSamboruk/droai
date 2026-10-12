"""Range estimate and body-NED approach/hold setpoints from a locked box.

`ApproachCommander` in `mavlink/approach_tx.py` sends these setpoints while a
target is locked. This module only computes the velocity command.
"""

from __future__ import annotations

import math
import time
from typing import Any, Sequence

import config

MAV_FRAME_BODY_NED = 8
MAV_FRAME_LOCAL_NED = 1
# Ignore position, acceleration, and yaw; use vx/vy/vz and yaw_rate.
POSITION_TARGET_TYPEMASK_VELOCITY_ONLY = 3527
POSITION_TARGET_TYPEMASK_VELOCITY_YAW_RATE = 1479
# SET_ATTITUDE_TARGET: ignore body rates, use attitude quaternion + thrust.
ATTITUDE_TARGET_TYPEMASK_ATTITUDE_THRUST = 7


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def box_geometry(box: Sequence[float]) -> tuple[float, float, float, float, float]:
    left, top, right, bottom = (float(value) for value in box[:4])
    width = max(0.0, right - left)
    height = max(0.0, bottom - top)
    center_x = (left + right) * 0.5
    center_y = (top + bottom) * 0.5
    return width, height, center_x, center_y, width * height


def frame_coords(box: Sequence[float], frame_size: tuple[float, float]) -> tuple[float, float]:
    """Normalized box center in the frame: 0 is middle, +x right, +y down, about [-1, 1]."""
    _, _, center_x, center_y, _ = box_geometry(box)
    frame_width, frame_height = (max(1.0, float(frame_size[0])), max(1.0, float(frame_size[1])))
    coord_x = (center_x - frame_width * 0.5) / (frame_width * 0.5)
    coord_y = (center_y - frame_height * 0.5) / (frame_height * 0.5)
    return clamp(coord_x, -1.5, 1.5), clamp(coord_y, -1.5, 1.5)


def focal_length_px(frame_width: float, hfov_deg: float, focal_px: float = 0.0) -> float:
    if focal_px > 0:
        return focal_px
    half_hfov = math.radians(hfov_deg) * 0.5
    if frame_width <= 0 or half_hfov <= 0:
        return 0.0
    return (frame_width * 0.5) / math.tan(half_hfov)


def real_width_m(class_name: str | None) -> float:
    widths = getattr(config, "TARGET_REAL_WIDTH_M", {})
    if class_name and class_name in widths:
        return float(widths[class_name])
    if class_name:
        lowered = class_name.casefold()
        for key, width in widths.items():
            if str(key).casefold() == lowered:
                return float(width)
    return float(getattr(config, "DEFAULT_TARGET_WIDTH_M", 1.8))


def range_from_pinhole(size_px: float, real_size_m: float, focal_px: float) -> float | None:
    if size_px <= 1.0 or real_size_m <= 0.0 or focal_px <= 0.0:
        return None
    return focal_px * real_size_m / size_px


def range_from_area(area_px: float, reference_area_px: float, reference_range_m: float) -> float | None:
    if area_px <= 1.0 or reference_area_px <= 1.0 or reference_range_m <= 0.0:
        return None
    return reference_range_m * math.sqrt(reference_area_px / area_px)


def estimate_range_m(
    box: Sequence[float],
    frame_size: tuple[float, float],
    class_name: str | None = None,
    reference_area_px: float | None = None,
    reference_range_m: float | None = None,
) -> dict[str, float | None]:
    width_px, height_px, _, _, area_px = box_geometry(box)
    frame_width, _ = frame_size
    focal_px = focal_length_px(
        float(frame_width),
        float(config.CAMERA_HFOV_DEG),
        float(config.CAMERA_FOCAL_PX),
    )
    width_real = real_width_m(class_name)
    pinhole_range = range_from_pinhole(width_px, width_real, focal_px)
    if pinhole_range is None:
        pinhole_range = range_from_pinhole(height_px, width_real, focal_px)
    area_range = None
    if reference_area_px and reference_range_m:
        area_range = range_from_area(area_px, reference_area_px, reference_range_m)
    range_m = pinhole_range if pinhole_range is not None else area_range
    if range_m is not None:
        range_m = clamp(range_m, float(config.APPROACH_RANGE_MIN_M), float(config.APPROACH_RANGE_MAX_M))
    return {
        "range_m": range_m,
        "pinhole_range_m": pinhole_range,
        "area_range_m": area_range,
        "box_width_px": width_px,
        "box_height_px": height_px,
        "box_area_px": area_px,
        "focal_px": focal_px,
    }


def approach_speed_m_s() -> float:
    return float(getattr(config, "APPROACH_SPEED_M_S", config.APPROACH_MAX_FORWARD_M_S))


def body_ned_velocity_target(
    vx: float,
    vy: float,
    vz: float = 0.0,
    yaw_rate: float = 0.0,
    coordinate_frame: int = MAV_FRAME_BODY_NED,
) -> dict[str, float | int]:
    """Fields for SET_POSITION_TARGET_LOCAL_NED (velocity + yaw rate, body NED)."""
    return {
        "time_boot_ms": 0,
        "coordinate_frame": coordinate_frame,
        "type_mask": POSITION_TARGET_TYPEMASK_VELOCITY_YAW_RATE,
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        "vx": float(vx),
        "vy": float(vy),
        "vz": float(vz),
        "afx": 0.0,
        "afy": 0.0,
        "afz": 0.0,
        "yaw": 0.0,
        "yaw_rate": float(yaw_rate),
    }


def attitude_target_from_forward_speed(
    forward_m_s: float,
    max_speed_m_s: float,
    max_pitch_rad: float,
    hover_thrust: float = 0.5,
) -> dict[str, float | int | tuple[float, float, float, float]]:
    """Optional SET_ATTITUDE_TARGET mapping. Prefer velocity setpoints for range hold."""
    scale = 0.0 if max_speed_m_s <= 0 else clamp(forward_m_s / max_speed_m_s, -1.0, 1.0)
    pitch = -max_pitch_rad * scale
    half = pitch * 0.5
    quaternion = (math.cos(half), 0.0, math.sin(half), 0.0)
    return {
        "type_mask": ATTITUDE_TARGET_TYPEMASK_ATTITUDE_THRUST,
        "q": quaternion,
        "body_roll_rate": 0.0,
        "body_pitch_rate": 0.0,
        "body_yaw_rate": 0.0,
        "thrust": float(hover_thrust),
        "pitch_rad": pitch,
    }


class PIDController:
    def __init__(
        self,
        kp: float,
        ki: float,
        kd: float,
        i_limit: float,
        output_min: float,
        output_max: float,
    ) -> None:
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.i_limit = abs(i_limit)
        self.output_min = output_min
        self.output_max = output_max
        self._integral = 0.0
        self._previous_error: float | None = None

    def reset(self) -> None:
        self._integral = 0.0
        self._previous_error = None

    def update(self, error: float, dt: float) -> float:
        if dt <= 0:
            return 0.0
        self._integral = clamp(
            self._integral + self.ki * error * dt,
            -self.i_limit,
            self.i_limit,
        )
        derivative = 0.0 if self._previous_error is None else (error - self._previous_error) / dt
        self._previous_error = error
        output = self.kp * error + self._integral + self.kd * derivative
        return clamp(output, self.output_min, self.output_max)


class ApproachHoldController:
    """Convert a locked box into body-NED velocity for approach and standoff hold."""

    def __init__(self) -> None:
        self._pid = PIDController(
            kp=float(config.APPROACH_PID_KP),
            ki=float(config.APPROACH_PID_KI),
            kd=float(config.APPROACH_PID_KD),
            i_limit=float(config.APPROACH_PID_I_LIMIT),
            output_min=-float(config.APPROACH_MAX_REVERSE_M_S),
            output_max=approach_speed_m_s(),
        )
        self._track_key: Any = object()
        self._reference_area_px: float | None = None
        self._reference_range_m: float | None = None
        self._last_update_at: float | None = None

    def reset(self) -> None:
        self._pid.reset()
        self._track_key = object()
        self._reference_area_px = None
        self._reference_range_m = None
        self._last_update_at = None

    def update(
        self,
        *,
        locked: bool,
        box: Sequence[float] | None,
        frame_size: tuple[float, float],
        class_name: str | None = None,
        track_id: Any = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        timestamp = time.monotonic() if now is None else now
        if not locked or box is None:
            self.reset()
            return self._status(
                "idle", 0.0, 0.0, 0.0, None, None, None, None, None,
                frame_size=frame_size,
            )

        track_key = (track_id, class_name)
        if track_key != self._track_key:
            self._pid.reset()
            self._track_key = track_key
            self._reference_area_px = None
            self._reference_range_m = None
            self._last_update_at = timestamp

        dt = 0.0 if self._last_update_at is None else max(0.0, timestamp - self._last_update_at)
        self._last_update_at = timestamp
        estimate = estimate_range_m(
            box,
            frame_size,
            class_name,
            self._reference_area_px,
            self._reference_range_m,
        )
        range_m = estimate["range_m"]
        area_px = estimate["box_area_px"]
        coord_x, coord_y = frame_coords(box, frame_size)
        if range_m is None:
            self._pid.reset()
            return self._status(
                "lost", 0.0, 0.0, 0.0, None, area_px, estimate, coord_x, coord_y,
                track_id=track_id,
                class_name=class_name,
                frame_size=frame_size,
            )

        if self._reference_area_px is None and area_px:
            self._reference_area_px = float(area_px)
            configured = float(config.APPROACH_REFERENCE_RANGE_M)
            self._reference_range_m = configured if configured > 0 else float(range_m)

        standoff = float(config.APPROACH_STANDOFF_M)
        error = float(range_m) - standoff
        width_px, _, _, _, _ = box_geometry(box)
        x_offset = coord_x

        if abs(error) <= float(config.APPROACH_HOLD_DEADBAND_M):
            self._pid.reset()
            closing_speed = 0.0
            state = "hold"
        else:
            closing_speed = self._pid.update(
                error,
                dt if dt > 0 else 1.0 / max(float(config.CAMERA_FPS), 1.0),
            )
            state = "approach" if error > 0 else "retreat"

        azimuth = clamp(x_offset, -1.0, 1.0) * math.radians(float(config.CAMERA_HFOV_DEG) * 0.5)
        forward = closing_speed * math.cos(azimuth)
        right = closing_speed * math.sin(azimuth)
        yaw_rate = clamp(
            float(config.APPROACH_YAW_KP) * x_offset,
            -float(config.APPROACH_MAX_YAW_RAD_S),
            float(config.APPROACH_MAX_YAW_RAD_S),
        )
        if width_px < 4 or state == "hold":
            yaw_rate = 0.0
            if state == "hold":
                right = 0.0
                forward = 0.0
        return self._status(
            state, forward, right, yaw_rate, float(range_m), area_px, estimate, error, coord_x, coord_y,
            track_id=track_id,
            class_name=class_name,
            frame_size=frame_size,
        )

    def _status(
        self,
        state: str,
        forward: float,
        right: float,
        yaw_rate: float,
        range_m: float | None,
        area_px: float | None,
        estimate: dict[str, float | None] | None,
        error: float | None = None,
        coord_x: float | None = None,
        coord_y: float | None = None,
        *,
        track_id: Any = None,
        class_name: str | None = None,
        frame_size: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        standoff = float(config.APPROACH_STANDOFF_M)
        return {
            "state": state,
            "range_m": range_m,
            "standoff_m": standoff,
            "range_error_m": error if error is not None else (None if range_m is None else range_m - standoff),
            "forward_m_s": forward,
            "right_m_s": right,
            "down_m_s": 0.0,
            "yaw_rate_rad_s": yaw_rate,
            "hold": state == "hold",
            "coord_x": coord_x,
            "coord_y": coord_y,
            "track_id": track_id,
            "class_name": class_name,
            "frame_width": None if frame_size is None else float(frame_size[0]),
            "frame_height": None if frame_size is None else float(frame_size[1]),
            "box_area_px": area_px,
            "estimate": estimate,
            "setpoint": body_ned_velocity_target(forward, right, 0.0, yaw_rate),
        }
