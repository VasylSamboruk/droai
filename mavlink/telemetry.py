from __future__ import annotations

import argparse
import copy
import json
import math
import threading
import time
from typing import Any, Callable, Protocol

import config
from NEW.visual_approach import (
    MAV_FRAME_BODY_NED,
    POSITION_TARGET_TYPEMASK_VELOCITY_YAW_RATE,
)


MESSAGE_TYPES = (
    "HEARTBEAT",
    "SYS_STATUS",
    "GLOBAL_POSITION_INT",
    "GPS_RAW_INT",
    "ATTITUDE",
    "LOCAL_POSITION_NED",
    "VFR_HUD",
    "RC_CHANNELS",
    "RC_CHANNELS_RAW",
)
MAV_MODE_FLAG_SAFETY_ARMED = 128
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1
MAV_TYPE_GCS = 6
MAV_CMD_NAV_GUIDED_ENABLE = 425
UNKNOWN_UINT16 = 65535
UNKNOWN_INT32 = -2147483648


class MAVLinkConnection(Protocol):
    def recv_match(
        self,
        type: list[str],
        blocking: bool,
        timeout: float,
    ) -> Any: ...

    def close(self) -> None: ...


ConnectionFactory = Callable[..., MAVLinkConnection]


class MAVLinkTelemetry:
    """Receive MAVLink telemetry and optionally send approach setpoints."""

    def __init__(
        self,
        connection_string: str = config.MAVLINK_CONNECTION,
        baud: int = config.MAVLINK_BAUD,
        heartbeat_timeout: float = config.MAVLINK_HEARTBEAT_TIMEOUT,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        if not connection_string.strip():
            raise ValueError("MAVLink connection string cannot be empty")
        if baud <= 0:
            raise ValueError("MAVLink baud rate must be positive")
        if heartbeat_timeout <= 0:
            raise ValueError("MAVLink heartbeat timeout must be positive")
        channels = (config.MAVLINK_TARGET_LOCK_CHANNEL, config.MAVLINK_TARGET_CYCLE_CHANNEL)
        if any(not 1 <= channel <= 18 for channel in channels):
            raise ValueError("MAVLink target-lock RC channels must be between 1 and 18")
        if channels[0] == channels[1]:
            raise ValueError("MAVLink target-lock and target-cycle channels must be different")
        if not 0 <= config.MAVLINK_FIX_MODE_CHANNEL <= 18:
            raise ValueError("MAVLINK_FIX_MODE_CHANNEL must be 0 (disabled) or between 1 and 18")
        if config.MAVLINK_FIX_MODE_PWM_US < 0:
            raise ValueError("MAVLINK_FIX_MODE_PWM_US cannot be negative")
        if config.MAVLINK_FIX_MODE_PWM_TOLERANCE_US < 0:
            raise ValueError("MAVLINK_FIX_MODE_PWM_TOLERANCE_US cannot be negative")

        self.connection_string = connection_string
        self.baud = baud
        self.heartbeat_timeout = heartbeat_timeout
        self._connection_factory = connection_factory
        self._connection: MAVLinkConnection | None = None
        self._io_lock = threading.Lock()
        self._last_heartbeat_at: float | None = None
        self._last_message_at: float | None = None
        self._last_rc_at: float | None = None
        self._state: dict[str, Any] = {
            "system_id": None,
            "component_id": None,
            "armed": None,
            "autopilot": None,
            "vehicle_type": None,
            "custom_mode": None,
            "last_message": None,
            "gps": {
                "fix_type": None,
                "satellites_visible": None,
                "latitude_deg": None,
                "longitude_deg": None,
                "altitude_m": None,
                "relative_altitude_m": None,
            },
            "velocity": {
                "ground_speed_m_s": None,
                "vertical_speed_m_s": None,
                "heading_deg": None,
            },
            "local_position_ned": {
                "x_m": None,
                "y_m": None,
                "z_m": None,
                "vx_m_s": None,
                "vy_m_s": None,
                "vz_m_s": None,
            },
            "attitude_deg": {
                "roll": None,
                "pitch": None,
                "yaw": None,
            },
            "rc_target_lock_switch_raw": None,
            "rc_target_cycle_switch_raw": None,
            "rc_channels_raw": {},
            "fix_mode_active": None,
            "battery": {
                "voltage_v": None,
                "remaining_percent": None,
            },
        }

    def connect(self) -> None:
        if self._connection is not None:
            return
        factory = self._connection_factory
        if factory is None:
            from pymavlink import mavutil

            factory = mavutil.mavlink_connection
        self._connection = factory(
            self.connection_string,
            baud=self.baud,
            autoreconnect=True,
        )

    def poll(self, timeout: float = 1.0) -> bool:
        if timeout < 0:
            raise ValueError("MAVLink poll timeout cannot be negative")
        if self._connection is None:
            raise RuntimeError("Call connect() before polling MAVLink telemetry")

        with self._io_lock:
            message = self._connection.recv_match(
                type=list(MESSAGE_TYPES),
                blocking=True,
                timeout=timeout,
            )
        if message is None:
            return False

        message_type = message.get_type()
        if message_type not in MESSAGE_TYPES:
            return False

        now = time.monotonic()
        self._last_message_at = now
        self._state["last_message"] = message_type
        src_system = message.get_srcSystem()
        src_component = message.get_srcComponent()
        if message_type == "HEARTBEAT" and int(message.type) != MAV_TYPE_GCS:
            self._state["system_id"] = src_system
            self._state["component_id"] = src_component
        elif self._state["system_id"] is None:
            self._state["system_id"] = src_system
            self._state["component_id"] = src_component

        if message_type == "HEARTBEAT":
            self._last_heartbeat_at = now
            base_mode = int(message.base_mode)
            if int(message.type) != MAV_TYPE_GCS:
                self._state.update(
                    armed=bool(base_mode & MAV_MODE_FLAG_SAFETY_ARMED),
                    autopilot=int(message.autopilot),
                    vehicle_type=int(message.type),
                    custom_mode=int(message.custom_mode),
                )
        elif message_type == "SYS_STATUS":
            voltage_mv = int(message.voltage_battery)
            remaining = int(message.battery_remaining)
            self._state["battery"].update(
                voltage_v=None if voltage_mv == UNKNOWN_UINT16 else voltage_mv / 1000,
                remaining_percent=remaining if 0 <= remaining <= 100 else None,
            )
        elif message_type == "GLOBAL_POSITION_INT":
            latitude = int(message.lat)
            longitude = int(message.lon)
            altitude = int(message.alt)
            relative_altitude = int(message.relative_alt)
            heading = int(message.hdg)
            self._state["gps"].update(
                latitude_deg=None if latitude == UNKNOWN_INT32 else latitude / 1e7,
                longitude_deg=None if longitude == UNKNOWN_INT32 else longitude / 1e7,
                altitude_m=None if altitude == UNKNOWN_INT32 else altitude / 1000,
                relative_altitude_m=(
                    None if relative_altitude == UNKNOWN_INT32 else relative_altitude / 1000
                ),
            )
            self._state["velocity"].update(
                ground_speed_m_s=(
                    math.hypot(int(message.vx), int(message.vy)) / 100
                ),
                vertical_speed_m_s=-int(message.vz) / 100,
                heading_deg=None if heading == UNKNOWN_UINT16 else heading / 100,
            )
        elif message_type == "GPS_RAW_INT":
            fix_type = int(message.fix_type)
            satellites = int(message.satellites_visible)
            self._state["gps"].update(
                fix_type=fix_type,
                satellites_visible=None if satellites == 255 else satellites,
            )
        elif message_type == "ATTITUDE":
            self._state["attitude_deg"].update(
                roll=math.degrees(float(message.roll)),
                pitch=math.degrees(float(message.pitch)),
                yaw=math.degrees(float(message.yaw)),
            )
        elif message_type == "LOCAL_POSITION_NED":
            self._state["local_position_ned"].update(
                x_m=float(message.x),
                y_m=float(message.y),
                z_m=float(message.z),
                vx_m_s=float(message.vx),
                vy_m_s=float(message.vy),
                vz_m_s=float(message.vz),
            )
        elif message_type == "VFR_HUD":
            heading = int(message.heading)
            self._state["velocity"].update(
                ground_speed_m_s=float(message.groundspeed),
                vertical_speed_m_s=float(message.climb),
                heading_deg=None if heading < 0 else float(heading),
            )
            self._state["gps"]["altitude_m"] = float(message.alt)
        elif message_type in {"RC_CHANNELS", "RC_CHANNELS_RAW"}:
            self._last_rc_at = now
            rc_channels = self._state["rc_channels_raw"]
            for channel in range(1, 19):
                field = f"chan{channel}_raw"
                if hasattr(message, field):
                    raw_value = int(getattr(message, field))
                    rc_channels[str(channel)] = (
                        raw_value if 0 < raw_value < UNKNOWN_UINT16 else None
                    )
            for channel, state_key in (
                (config.MAVLINK_TARGET_LOCK_CHANNEL, "rc_target_lock_switch_raw"),
                (config.MAVLINK_TARGET_CYCLE_CHANNEL, "rc_target_cycle_switch_raw"),
            ):
                self._state[state_key] = rc_channels.get(str(channel))

            fix_channel = config.MAVLINK_FIX_MODE_CHANNEL
            fix_pwm = config.MAVLINK_FIX_MODE_PWM_US
            fix_raw = rc_channels.get(str(fix_channel)) if fix_channel else None
            self._state["fix_mode_active"] = (
                None
                if fix_raw is None or not fix_pwm
                else abs(fix_raw - fix_pwm) <= config.MAVLINK_FIX_MODE_PWM_TOLERANCE_US
            )

        return True

    def send_set_mode(self, custom_mode: int) -> str | None:
        mav, system_id, _ = self._sender()
        if mav is None:
            return "MAVLink connection cannot send"
        try:
            with self._io_lock:
                mav.set_mode_send(
                    system_id,
                    MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                    int(custom_mode),
                )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            return str(error)
        return None

    def send_guided_enable(self, enabled: bool) -> str | None:
        mav, system_id, component_id = self._sender()
        if mav is None:
            return "MAVLink connection cannot send"
        try:
            with self._io_lock:
                mav.command_long_send(
                    system_id,
                    component_id,
                    MAV_CMD_NAV_GUIDED_ENABLE,
                    0,
                    1.0 if enabled else 0.0,
                    0, 0, 0, 0, 0, 0,
                )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            return str(error)
        return None

    def send_body_ned_velocity(
        self,
        vx: float,
        vy: float,
        vz: float = 0.0,
        yaw_rate: float = 0.0,
        coordinate_frame: int = MAV_FRAME_BODY_NED,
        type_mask: int = POSITION_TARGET_TYPEMASK_VELOCITY_YAW_RATE,
    ) -> str | None:
        mav, system_id, component_id = self._sender()
        if mav is None:
            return "MAVLink connection cannot send"
        try:
            with self._io_lock:
                mav.set_position_target_local_ned_send(
                    int(time.time() * 1000) & 0xFFFFFFFF,
                    system_id,
                    component_id,
                    int(coordinate_frame),
                    int(type_mask),
                    0, 0, 0,
                    float(vx), float(vy), float(vz),
                    0, 0, 0,
                    0, float(yaw_rate),
                )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            return str(error)
        return None

    def send_rc_channels_override(self, channels: list[int]) -> str | None:
        mav, system_id, component_id = self._sender()
        if mav is None:
            return "MAVLink connection cannot send"
        padded = list(channels)
        while len(padded) < 8:
            padded.append(UNKNOWN_UINT16)
        try:
            with self._io_lock:
                mav.rc_channels_override_send(system_id, component_id, *padded[:18])
        except TypeError:
            try:
                with self._io_lock:
                    mav.rc_channels_override_send(system_id, component_id, *padded[:8])
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
                return str(error)
        except (AttributeError, OSError, RuntimeError, ValueError) as error:
            return str(error)
        return None

    def _sender(self) -> tuple[Any, int, int]:
        connection = self._connection
        if connection is None:
            return None, 1, 1
        mav = getattr(connection, "mav", None)
        system_id = int(self._state["system_id"] or getattr(connection, "target_system", 1) or 1)
        component_id = int(
            self._state["component_id"] or getattr(connection, "target_component", 1) or 1
        )
        return mav, system_id, component_id

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        heartbeat_age = (
            None if self._last_heartbeat_at is None else max(0.0, now - self._last_heartbeat_at)
        )
        message_age = (
            None if self._last_message_at is None else max(0.0, now - self._last_message_at)
        )
        rc_age = None if self._last_rc_at is None else max(0.0, now - self._last_rc_at)
        rc_timeout = float(getattr(config, "FIX_RC_LOSS_TIMEOUT_S", 1.0))
        return {
            **copy.deepcopy(self._state),
            "connection": self.connection_string,
            "connected": heartbeat_age is not None and heartbeat_age <= self.heartbeat_timeout,
            "heartbeat_age_s": None if heartbeat_age is None else round(heartbeat_age, 2),
            "last_message_age_s": None if message_age is None else round(message_age, 2),
            "rc_age_s": None if rc_age is None else round(rc_age, 2),
            "rc_link_ok": None if rc_age is None else rc_age <= rc_timeout,
            "fix_mode_active": (
                self._state["fix_mode_active"]
                if rc_age is not None and rc_age <= rc_timeout
                else None
            ),
        }

    def close(self) -> None:
        with self._io_lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only MAVLink telemetry monitor")
    if not config.MAVLINK_ENABLED:
        parser.error("Set MAVLINK_ENABLED=1 to start the telemetry receiver")

    telemetry = MAVLinkTelemetry()
    telemetry.connect()
    try:
        while True:
            telemetry.poll(timeout=1.0)
            print(json.dumps(telemetry.status(), ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        return 0
    finally:
        telemetry.close()


if __name__ == "__main__":
    raise SystemExit(main())
