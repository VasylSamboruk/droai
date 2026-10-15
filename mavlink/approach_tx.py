from __future__ import annotations

import time
from typing import Any

import config
from fix.fix_acro_control import AcroFixController
from NEW.visual_approach import (
    POSITION_TARGET_TYPEMASK_VELOCITY_YAW_RATE,
    body_ned_velocity_target,
)

MAV_AUTOPILOT_PX4 = 12
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1
MAV_CMD_NAV_GUIDED_ENABLE = 425
PX4_CUSTOM_MAIN_MODE_OFFBOARD = 6
RC_IGNORE_US = 65535
RC_RELEASE_US = 0


def _zero_setpoint() -> dict[str, float | int]:
    return body_ned_velocity_target(0.0, 0.0, 0.0)


def approach_control_mode() -> str:
    return str(getattr(config, "APPROACH_CONTROL_MODE", "acro")).strip().casefold()


def guided_custom_mode(autopilot: int | None) -> int:
    if autopilot == MAV_AUTOPILOT_PX4:
        return PX4_CUSTOM_MAIN_MODE_OFFBOARD << 16
    return int(config.MAVLINK_APPROACH_GUIDED_MODE)


def acro_custom_mode() -> int:
    return int(getattr(config, "MAVLINK_APPROACH_ACRO_MODE", 2))


class ApproachCommander:
    """Take control while channel 8 is held: GUIDED velocity or ACRO RC override."""

    def __init__(self, telemetry: Any) -> None:
        self._telemetry = telemetry
        self._engaged = False
        self._mode = "idle"
        self._previous_mode: int | None = None
        self._last_send_at = 0.0
        self._failsafe_sent = False
        self._acro = AcroFixController()
        self._status: dict[str, Any] = self._idle_status("idle")

    def status(self) -> dict[str, Any]:
        return dict(self._status)

    def update(
        self,
        *,
        active: bool,
        setpoint: dict[str, Any] | None,
        telemetry_status: dict[str, Any],
        now: float | None = None,
        guidance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        timestamp = time.monotonic() if now is None else now
        if not config.MAVLINK_APPROACH_TX:
            return self.disengage(telemetry_status)
        if not active:
            self._failsafe_sent = False
            return self.disengage(telemetry_status)
        if self._failsafe_sent:
            return self.status()
        if not telemetry_status.get("connected"):
            return self._maybe_failsafe(telemetry_status, "link_loss")
        if telemetry_status.get("rc_link_ok") is False:
            return self._maybe_failsafe(telemetry_status, "rc_loss")
        if (
            bool(getattr(config, "MAVLINK_APPROACH_REQUIRE_FIX_MODE", True))
            and telemetry_status.get("fix_mode_active") is not True
        ):
            state = (
                "waiting_fix_mode"
                if telemetry_status.get("fix_mode_active") is None
                else "fix_mode_off"
            )
            if self._engaged:
                self.disengage(telemetry_status, reason=state)
            self._status = self._idle_status(state)
            return self.status()
        if config.MAVLINK_APPROACH_REQUIRE_ARMED and not telemetry_status.get("armed"):
            self._status = self._idle_status("waiting_armed")
            return self.status()

        if approach_control_mode() == "guided":
            return self._update_guided(setpoint, telemetry_status, timestamp)
        return self._update_acro(guidance, telemetry_status, timestamp)

    def disengage(
        self,
        telemetry_status: dict[str, Any] | None = None,
        reason: str = "idle",
    ) -> dict[str, Any]:
        if not self._engaged:
            self._status = self._idle_status(reason)
            return self.status()

        telemetry_status = telemetry_status or {}
        if self._mode == "acro":
            self._release_override()
        else:
            self._telemetry.send_body_ned_velocity(0.0, 0.0, 0.0)
            self._telemetry.send_guided_enable(False)
        restore = self._previous_mode
        engaged_mode = (
            acro_custom_mode()
            if self._mode == "acro"
            else guided_custom_mode(telemetry_status.get("autopilot"))
        )
        if restore is None:
            restore = int(config.MAVLINK_APPROACH_HOLD_MODE)
        self._telemetry.send_set_mode(restore)
        self._engaged = False
        self._mode = "idle"
        self._previous_mode = None
        self._acro.reset()
        self._status = self._idle_status(reason)
        return self.status()

    def _update_guided(
        self,
        setpoint: dict[str, Any] | None,
        telemetry_status: dict[str, Any],
        timestamp: float,
    ) -> dict[str, Any]:
        error = self._engage(telemetry_status, "guided")
        if error is not None:
            self._status = self._idle_status("error", error=error)
            return self.status()

        rate = max(float(config.MAVLINK_APPROACH_RATE_HZ), 1.0)
        if timestamp - self._last_send_at < 1.0 / rate:
            return self.status()

        target = setpoint if setpoint is not None else _zero_setpoint()
        error = self._telemetry.send_body_ned_velocity(
            float(target.get("vx", 0.0)),
            float(target.get("vy", 0.0)),
            float(target.get("vz", 0.0)),
            yaw_rate=float(target.get("yaw_rate", 0.0)),
            coordinate_frame=int(target.get("coordinate_frame", 8)),
            type_mask=int(target.get("type_mask", POSITION_TARGET_TYPEMASK_VELOCITY_YAW_RATE)),
        )
        self._last_send_at = timestamp
        self._status = {
            "state": "error" if error else "transmitting",
            "engaged": True,
            "control_mode": "guided",
            "guided_mode": guided_custom_mode(telemetry_status.get("autopilot")),
            "error": error,
            "vx": float(target.get("vx", 0.0)),
            "vy": float(target.get("vy", 0.0)),
            "vz": float(target.get("vz", 0.0)),
        }
        return self.status()

    def _update_acro(
        self,
        guidance: dict[str, Any] | None,
        telemetry_status: dict[str, Any],
        timestamp: float,
    ) -> dict[str, Any]:
        error = self._engage(telemetry_status, "acro")
        if error is not None:
            self._status = self._idle_status("error", error=error)
            return self.status()

        rate = max(float(getattr(config, "FIX_ACRO_RATE_HZ", config.MAVLINK_APPROACH_RATE_HZ)), 1.0)
        if timestamp - self._last_send_at < 1.0 / rate:
            return self.status()

        dt = 1.0 / rate
        if self._last_send_at > 0:
            dt = max(dt, timestamp - self._last_send_at)
        guidance = guidance or {}
        attitude = telemetry_status.get("attitude_deg") or {}
        frame_width = guidance.get("frame_width")
        frame_height = guidance.get("frame_height")
        frame_size = (
            (float(frame_width), float(frame_height))
            if frame_width is not None and frame_height is not None
            else None
        )
        roll_i, pitch_i, yaw_i, thr_i, dbg = self._acro.compute(
            float(guidance.get("coord_x") or 0.0),
            float(guidance.get("coord_y") or 0.0),
            dt,
            roll_deg=attitude.get("roll"),
            pitch_deg=attitude.get("pitch"),
            frame_size=frame_size,
            target_key=(guidance.get("track_id"), guidance.get("class_name")),
            range_error_m=guidance.get("range_error_m"),
            hold=bool(guidance.get("hold")),
        )
        channels = self._override_channels(roll_i, pitch_i, yaw_i, thr_i, telemetry_status)
        error = self._telemetry.send_rc_channels_override(channels)
        self._last_send_at = timestamp
        self._status = {
            "state": "error" if error else "transmitting",
            "engaged": True,
            "control_mode": "acro",
            "guided_mode": acro_custom_mode(),
            "error": error,
            "roll_pwm": roll_i,
            "pitch_pwm": pitch_i,
            "yaw_pwm": yaw_i,
            "throttle_pwm": thr_i,
            "vx": 0.0,
            "vy": 0.0,
            "vz": 0.0,
            "acro": dbg,
        }
        return self.status()

    def _engage(self, telemetry_status: dict[str, Any], mode: str) -> str | None:
        if self._engaged and self._mode == mode:
            return None
        if self._engaged and self._mode != mode:
            self.disengage(telemetry_status, reason="mode_switch")
        current_mode = telemetry_status.get("custom_mode")
        self._previous_mode = int(current_mode) if current_mode is not None else None
        if mode == "acro":
            flight_mode = acro_custom_mode()
            error = self._telemetry.send_set_mode(flight_mode)
            if error is not None:
                return error
            self._acro.reset()
        else:
            flight_mode = guided_custom_mode(telemetry_status.get("autopilot"))
            error = self._telemetry.send_set_mode(flight_mode)
            if error is not None:
                return error
            error = self._telemetry.send_guided_enable(True)
            if error is not None:
                return error
        self._engaged = True
        self._mode = mode
        self._status = {
            "state": "engaging",
            "engaged": True,
            "control_mode": mode,
            "guided_mode": flight_mode,
            "error": None,
            "vx": 0.0,
            "vy": 0.0,
            "vz": 0.0,
        }
        return None

    def _maybe_failsafe(self, telemetry_status: dict[str, Any], reason: str) -> dict[str, Any]:
        if not bool(getattr(config, "FIX_RC_LOSS_FAILSAFE_ENABLED", True)):
            return self.disengage(telemetry_status, reason=reason)
        if not self._engaged and not self._failsafe_sent:
            return self.disengage(telemetry_status, reason=reason)
        if self._failsafe_sent:
            return self.status()
        self._failsafe_sent = True
        repeats = max(1, int(getattr(config, "FIX_RC_LOSS_RTL_REPEATS", 3)))
        rtl_mode = int(getattr(config, "FIX_FAILSAFE_MODE_ID", 6))
        if bool(getattr(config, "FIX_RTL_CLEAR_OVERRIDE_ON_RC_LOSS", False)):
            self._release_override()
        for _ in range(repeats):
            self._telemetry.send_set_mode(rtl_mode)
        self._engaged = False
        self._mode = "idle"
        self._previous_mode = None
        self._acro.reset()
        self._status = self._idle_status("failsafe", error=reason)
        self._status["failsafe"] = True
        return self.status()

    def _release_override(self) -> None:
        n_ch = int(getattr(config, "RC_OVERRIDE_CHANNEL_COUNT", 8))
        bursts = max(1, int(getattr(config, "FIX_RC_LOSS_CLEAR_OVERRIDE_BURSTS", 3)))
        channels = [RC_RELEASE_US] * n_ch
        for _ in range(bursts):
            self._telemetry.send_rc_channels_override(channels)

    @staticmethod
    def _override_channels(
        roll: int,
        pitch: int,
        yaw: int,
        throttle: int,
        telemetry_status: dict[str, Any],
    ) -> list[int]:
        n_ch = max(8, int(getattr(config, "RC_OVERRIDE_CHANNEL_COUNT", 8)))
        channels = [RC_IGNORE_US] * n_ch
        stick = {
            int(getattr(config, "OVERRIDE_ROLL_CHANNEL_1_BASED", 1)): roll,
            int(getattr(config, "OVERRIDE_PITCH_CHANNEL_1_BASED", 2)): pitch,
            int(getattr(config, "OVERRIDE_THROTTLE_CHANNEL_1_BASED", 3)): throttle,
            int(getattr(config, "OVERRIDE_YAW_CHANNEL_1_BASED", 4)): yaw,
        }
        rc_raw = telemetry_status.get("rc_channels_raw") or {}
        for channel in range(1, n_ch + 1):
            if channel in stick:
                channels[channel - 1] = int(stick[channel])
                continue
            raw = rc_raw.get(str(channel))
            if raw:
                channels[channel - 1] = int(raw)
        return channels

    @staticmethod
    def _idle_status(state: str, error: str | None = None) -> dict[str, Any]:
        return {
            "state": state,
            "engaged": False,
            "control_mode": approach_control_mode(),
            "guided_mode": None,
            "error": error,
            "vx": 0.0,
            "vy": 0.0,
            "vz": 0.0,
        }
