"""Frame-error PID → RC sticks for auto-approach while channel 8 is held."""

from __future__ import annotations

import math
from typing import Any

import config
from fix.fix_pid import PID


def _cfg(name: str, default: float) -> float:
    return float(getattr(config, name, default))


class AcroFixController:
    """Aim at a locked box with RC PWM. Geometry is selected in config."""

    def __init__(self) -> None:
        self._pid_aim_x: PID | None = None
        self._pid_aim_y: PID | None = None
        self._pid_level: PID | None = None
        self._smooth_err_x = 0.0
        self._smooth_err_y = 0.0
        self._pitch_track_key: Any = object()
        self._target_world_elevation_rad: float | None = None
        self._out_throttle = 1500.0
        self._out_roll = 1500.0
        self._out_pitch = 1500.0
        self._out_yaw = 1500.0
        self._build_pids()

    def _build_pids(self) -> None:
        i_max = _cfg("FIX_ACRO_I_MAX", 0.35)
        self._pid_aim_x = PID(
            _cfg("FIX_ACRO_ROLL_KP", 0.35),
            _cfg("FIX_ACRO_ROLL_KI", 0.05),
            _cfg("FIX_ACRO_ROLL_KD", 0.18),
            out_max=_cfg("FIX_ACRO_ROLL_MAX", 0.5),
            i_max=i_max,
        )
        self._pid_aim_y = PID(
            _cfg("FIX_ACRO_PITCH_KP", 0.35),
            _cfg("FIX_ACRO_PITCH_KI", 0.05),
            _cfg("FIX_ACRO_PITCH_KD", 0.18),
            out_max=_cfg("FIX_ACRO_PITCH_MAX", 0.5),
            i_max=i_max,
        )
        self._pid_level = PID(
            _cfg("FIX_ACRO_LEVEL_KP", 0.40),
            _cfg("FIX_ACRO_LEVEL_KI", 0.0),
            _cfg("FIX_ACRO_LEVEL_KD", 0.10),
            out_max=_cfg("FIX_ACRO_LEVEL_MAX", 0.35),
            i_max=i_max,
        )

    def reset(self) -> None:
        self._build_pids()
        self._smooth_err_x = 0.0
        self._smooth_err_y = 0.0
        self._pitch_track_key = object()
        self._target_world_elevation_rad = None
        self._out_throttle = self._clamp_pwm(_cfg("FIX_ACRO_HOLD_THROTTLE_US", 1500))
        self._out_roll = 1500.0
        self._out_pitch = 1500.0
        self._out_yaw = 1500.0

    @staticmethod
    def _deadband(v: float, db: float) -> float:
        if db <= 0.0:
            return v
        if abs(v) <= db:
            return 0.0
        span = max(1.0 - db, 1e-6)
        mag = min(1.0, (abs(v) - db) / span)
        return mag if v > 0 else -mag

    @staticmethod
    def _clamp_pwm(v: float) -> float:
        return max(1000.0, min(2000.0, v))

    @staticmethod
    def _slew(current: float, target: float, max_step: float) -> float:
        if max_step <= 0.0:
            return target
        if target > current + max_step:
            return current + max_step
        if target < current - max_step:
            return current - max_step
        return target

    @staticmethod
    def _norm_to_pwm(v: float) -> float:
        return max(1000.0, min(2000.0, 1500.0 + v * 500.0))

    @staticmethod
    def _soft_zone_factor(err: float, zone: float, scale: float) -> float:
        if zone <= 0.0:
            return 1.0
        a = abs(err)
        if a >= zone:
            return 1.0
        scale = max(0.0, min(1.0, scale))
        return scale + (1.0 - scale) * (a / zone)

    def _level_norm(self, roll_deg: float | None, dt: float) -> tuple[float, float | None]:
        if not bool(getattr(config, "FIX_ACRO_LEVEL_ENABLED", True)):
            return 0.0, None
        if roll_deg is None:
            return 0.0, None
        deadband_deg = _cfg("FIX_ACRO_LEVEL_DEADBAND_DEG", 2.0)
        ref_deg = max(5.0, _cfg("FIX_ACRO_LEVEL_REF_DEG", 45.0))
        level_sign = _cfg("FIX_ACRO_LEVEL_SIGN", 1.0)
        roll_err_deg = 0.0 - float(roll_deg)
        if abs(roll_err_deg) <= deadband_deg:
            roll_err_deg = 0.0
        level_err = max(-1.0, min(1.0, roll_err_deg / ref_deg))
        return level_sign * self._pid_level.update(level_err, dt), float(roll_deg)

    def _pitch_compensated_target_y(
        self,
        coord_y: float,
        pitch_deg: float | None,
        frame_size: tuple[float, float] | None,
        target_key: Any,
    ) -> tuple[float, bool, bool]:
        default_target = _cfg("FIX_ACRO_TARGET_Y", 0.05)
        if not bool(getattr(config, "APPROACH_PITCH_COMPENSATION_ENABLED", False)):
            return default_target, False, True
        if pitch_deg is None or frame_size is None:
            return default_target, False, True

        if target_key != self._pitch_track_key:
            self._pitch_track_key = target_key
            self._target_world_elevation_rad = None

        frame_width = max(float(frame_size[0]), 1.0)
        frame_height = max(float(frame_size[1]), 1.0)
        half_hfov = math.radians(float(config.CAMERA_HFOV_DEG)) * 0.5
        tan_half_vfov = (frame_height / frame_width) * math.tan(half_hfov)
        if tan_half_vfov <= 0.0:
            return default_target, False, True

        body_pitch = math.radians(float(pitch_deg))
        mount_down = math.radians(
            float(getattr(config, "CAMERA_MOUNT_PITCH_DOWN_DEG", 0.0))
        )
        pixel_angle_down = math.atan(float(coord_y) * tan_half_vfov)
        # Hold the target's world line-of-sight while the rigid camera follows body pitch.
        target_elevation = body_pitch - mount_down - pixel_angle_down
        if self._target_world_elevation_rad is None:
            self._target_world_elevation_rad = target_elevation

        desired_pixel_angle_down = (
            body_pitch - mount_down - self._target_world_elevation_rad
        )
        vertical_half_fov = math.atan(tan_half_vfov)
        if abs(desired_pixel_angle_down) >= vertical_half_fov:
            return float(coord_y), True, False
        desired_y = math.tan(desired_pixel_angle_down) / tan_half_vfov
        if abs(desired_y) > 1.0:
            return float(coord_y), True, False
        return desired_y + default_target, True, True

    def compute(
        self,
        coord_x: float,
        coord_y: float,
        dt: float,
        *,
        roll_deg: float | None = None,
        pitch_deg: float | None = None,
        frame_size: tuple[float, float] | None = None,
        target_key: Any = None,
        range_error_m: float | None = None,
        hold: bool = False,
    ) -> tuple[int, int, int, int, dict[str, Any]]:
        target_x = _cfg("FIX_ACRO_TARGET_X", 0.0)
        target_y = _cfg("FIX_ACRO_TARGET_Y", 0.05)
        deadband = _cfg("FIX_ACRO_DEADBAND", 0.03)
        alpha = min(1.0, max(0.0, _cfg("FIX_ACRO_INPUT_SMOOTH_ALPHA", 0.4)))
        slew_step = max(0.0, _cfg("FIX_ACRO_PWM_SLEW_US_PER_S", 900.0)) * dt
        geometry = str(getattr(config, "APPROACH_ACRO_GEOMETRY", "copter")).casefold()

        err_x = self._deadband(coord_x - target_x, deadband)
        target_y, pitch_compensation_active, target_in_view = self._pitch_compensated_target_y(
            coord_y,
            pitch_deg,
            frame_size,
            target_key,
        )
        err_y = self._deadband(coord_y - target_y, deadband)
        self._smooth_err_x = alpha * err_x + (1.0 - alpha) * self._smooth_err_x
        self._smooth_err_y = alpha * err_y + (1.0 - alpha) * self._smooth_err_y

        aim_x = self._pid_aim_x.update(self._smooth_err_x, dt)
        aim_y = self._pid_aim_y.update(self._smooth_err_y, dt)
        soft_zone = _cfg("FIX_ACRO_SOFT_ZONE", 0.15)
        soft_scale = _cfg("FIX_ACRO_SOFT_ZONE_SCALE", 0.3)
        aim_x *= self._soft_zone_factor(self._smooth_err_x, soft_zone, soft_scale)
        aim_y *= self._soft_zone_factor(self._smooth_err_y, soft_zone, soft_scale)

        x_sign = _cfg("FIX_ACRO_ROLL_SIGN", 1.0)
        y_sign = _cfg("FIX_ACRO_PITCH_SIGN", 1.0)
        level_norm, used_roll = self._level_norm(roll_deg, dt)

        forward = 0.0
        if not hold and target_in_view and range_error_m is not None:
            ref = max(1.0, _cfg("FIX_ACRO_RANGE_REF_M", 10.0))
            forward = max(-1.0, min(1.0, float(range_error_m) / ref)) * _cfg(
                "FIX_ACRO_FORWARD_GAIN", 0.35
            )
            forward *= _cfg("FIX_ACRO_PITCH_FORWARD_SIGN", 1.0)

        if geometry == "rocket":
            roll_norm = x_sign * aim_x
            pitch_norm = y_sign * aim_y + forward
            yaw_norm = level_norm
        else:
            roll_norm = level_norm
            pitch_norm = y_sign * aim_y + forward
            yaw_norm = x_sign * aim_x

        cruise = _cfg("FIX_ACRO_THROTTLE_US", 1500)
        hover = _cfg("FIX_ACRO_HOLD_THROTTLE_US", 1500)
        target_thr = hover if hold else cruise
        target_roll = self._norm_to_pwm(roll_norm)
        target_pitch = self._norm_to_pwm(pitch_norm)
        target_yaw = self._norm_to_pwm(yaw_norm)

        self._out_roll = self._slew(self._out_roll, target_roll, slew_step)
        self._out_pitch = self._slew(self._out_pitch, target_pitch, slew_step)
        self._out_yaw = self._slew(self._out_yaw, target_yaw, slew_step)
        self._out_throttle = self._slew(self._out_throttle, self._clamp_pwm(target_thr), slew_step)

        dbg = {
            "geometry": geometry,
            "hold": hold,
            "err_x": err_x,
            "err_y": err_y,
            "target_y": target_y,
            "pitch_compensation_active": pitch_compensation_active,
            "target_in_view": target_in_view,
            "smooth_x": self._smooth_err_x,
            "smooth_y": self._smooth_err_y,
            "roll_norm": roll_norm,
            "pitch_norm": pitch_norm,
            "yaw_norm": yaw_norm,
            "forward": forward,
            "roll_deg": used_roll,
        }
        return (
            int(round(self._out_roll)),
            int(round(self._out_pitch)),
            int(round(self._out_yaw)),
            int(round(self._out_throttle)),
            dbg,
        )
