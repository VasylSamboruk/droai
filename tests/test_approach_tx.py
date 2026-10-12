from __future__ import annotations

import unittest
from unittest.mock import patch

from NEW.visual_approach import body_ned_velocity_target
from mavlink.approach_tx import ApproachCommander, guided_custom_mode
from mavlink.telemetry import MAVLinkTelemetry
from test_mavlink_telemetry import FakeMessage


class RecordingMav:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def set_mode_send(self, *args: object) -> None:
        self.calls.append(("set_mode", args))

    def command_long_send(self, *args: object) -> None:
        self.calls.append(("command_long", args))

    def set_position_target_local_ned_send(self, *args: object) -> None:
        self.calls.append(("position_target", args))

    def rc_channels_override_send(self, *args: object) -> None:
        self.calls.append(("rc_override", args))


class RecordingConnection:
    def __init__(self, messages: list[FakeMessage | None]) -> None:
        self.messages = messages
        self.mav = RecordingMav()
        self.closed = False

    def recv_match(self, type: list[str], blocking: bool, timeout: float) -> FakeMessage | None:
        return self.messages.pop(0) if self.messages else None

    def close(self) -> None:
        self.closed = True


class ApproachTxTests(unittest.TestCase):
    def _telemetry(self, armed: bool = True, custom_mode: int = 5) -> tuple[MAVLinkTelemetry, RecordingMav]:
        connection = RecordingConnection(
            [
                FakeMessage(
                    "HEARTBEAT",
                    base_mode=128 if armed else 0,
                    autopilot=3,
                    type=2,
                    custom_mode=custom_mode,
                )
            ]
        )
        telemetry = MAVLinkTelemetry(connection_factory=lambda *_args, **_kwargs: connection)
        telemetry.connect()
        telemetry.poll()
        return telemetry, connection.mav

    def test_lock_switches_guided_and_streams_body_velocity(self) -> None:
        telemetry, mav = self._telemetry()
        commander = ApproachCommander(telemetry)
        setpoint = body_ned_velocity_target(1.25, -0.2, 0.0)
        with patch("config.APPROACH_CONTROL_MODE", "guided"), patch("config.MAVLINK_APPROACH_TX", True), patch("config.MAVLINK_APPROACH_REQUIRE_ARMED", True):
            status = commander.update(
                active=True,
                setpoint=setpoint,
                telemetry_status={**telemetry.status(), "fix_mode_active": True},
                now=5.0,
            )
        self.assertEqual(status["state"], "transmitting")
        self.assertEqual(mav.calls[0][0], "set_mode")
        self.assertEqual(mav.calls[0][1][2], 4)
        self.assertEqual(mav.calls[1][0], "command_long")
        self.assertEqual(mav.calls[1][1][2], 425)
        self.assertEqual(mav.calls[1][1][4], 1.0)
        self.assertEqual(mav.calls[2][0], "position_target")
        self.assertEqual(mav.calls[2][1][8], 1.25)
        self.assertEqual(mav.calls[2][1][9], -0.2)

    def test_unlock_zeros_velocity_and_restores_previous_mode(self) -> None:
        telemetry, mav = self._telemetry(custom_mode=5)
        commander = ApproachCommander(telemetry)
        with patch("config.APPROACH_CONTROL_MODE", "guided"), patch("config.MAVLINK_APPROACH_TX", True), patch("config.MAVLINK_APPROACH_REQUIRE_ARMED", True):
            commander.update(
                active=True,
                setpoint=body_ned_velocity_target(0.8, 0.0, 0.0),
                telemetry_status={**telemetry.status(), "fix_mode_active": True},
                now=5.0,
            )
            mav.calls.clear()
            status = commander.update(
                active=False,
                setpoint=None,
                telemetry_status={**telemetry.status(), "fix_mode_active": True},
                now=5.2,
            )
        self.assertEqual(status["state"], "idle")
        self.assertFalse(status["engaged"])
        self.assertEqual(mav.calls[0][0], "position_target")
        self.assertEqual(mav.calls[0][1][8], 0.0)
        self.assertEqual(mav.calls[1][0], "command_long")
        self.assertEqual(mav.calls[1][1][4], 0.0)
        self.assertEqual(mav.calls[2][0], "set_mode")
        self.assertEqual(mav.calls[2][1][2], 5)

    def test_waits_for_armed_before_sending(self) -> None:
        telemetry, mav = self._telemetry(armed=False)
        commander = ApproachCommander(telemetry)
        with patch("config.APPROACH_CONTROL_MODE", "guided"), patch("config.MAVLINK_APPROACH_TX", True), patch("config.MAVLINK_APPROACH_REQUIRE_ARMED", True):
            status = commander.update(
                active=True,
                setpoint=body_ned_velocity_target(1.0, 0.0, 0.0),
                telemetry_status={**telemetry.status(), "fix_mode_active": True},
                now=5.0,
            )
        self.assertEqual(status["state"], "waiting_armed")
        self.assertEqual(mav.calls, [])

    def test_fix_switch_is_required_before_any_flight_command(self) -> None:
        telemetry, mav = self._telemetry()
        commander = ApproachCommander(telemetry)
        with patch("config.APPROACH_CONTROL_MODE", "acro"), patch(
            "config.MAVLINK_APPROACH_TX", True
        ), patch("config.MAVLINK_APPROACH_REQUIRE_FIX_MODE", True):
            unknown = commander.update(
                active=True,
                setpoint=None,
                telemetry_status={**telemetry.status(), "fix_mode_active": None},
                now=5.0,
            )
            self.assertEqual(unknown["state"], "waiting_fix_mode")
            self.assertEqual(mav.calls, [])
            off = commander.update(
                active=True,
                setpoint=None,
                telemetry_status={**telemetry.status(), "fix_mode_active": False},
                now=5.1,
            )
        self.assertEqual(off["state"], "fix_mode_off")
        self.assertEqual(mav.calls, [])

    def test_acro_switch_sets_acro_and_streams_rc_override(self) -> None:
        telemetry, mav = self._telemetry()
        commander = ApproachCommander(telemetry)
        with patch("config.APPROACH_CONTROL_MODE", "acro"), patch("config.MAVLINK_APPROACH_TX", True), patch(
            "config.MAVLINK_APPROACH_REQUIRE_ARMED", True
        ), patch("config.FIX_ACRO_PWM_SLEW_US_PER_S", 0.0), patch("config.FIX_ACRO_LEVEL_ENABLED", False):
            status = commander.update(
                active=True,
                setpoint=None,
                telemetry_status={**telemetry.status(), "fix_mode_active": True},
                now=5.0,
                guidance={"coord_x": 0.6, "coord_y": 0.0, "range_error_m": 8.0, "hold": False},
            )
        self.assertEqual(status["state"], "transmitting")
        self.assertEqual(status["control_mode"], "acro")
        self.assertEqual(mav.calls[0][0], "set_mode")
        self.assertEqual(mav.calls[0][1][2], 2)
        override = next(call for call in mav.calls if call[0] == "rc_override")
        self.assertGreater(override[1][5], 1500)
        self.assertGreater(status["yaw_pwm"], 1500)

    def test_acro_unlock_releases_override_and_restores_mode(self) -> None:
        telemetry, mav = self._telemetry(custom_mode=5)
        commander = ApproachCommander(telemetry)
        with patch("config.APPROACH_CONTROL_MODE", "acro"), patch("config.MAVLINK_APPROACH_TX", True), patch(
            "config.FIX_RC_LOSS_CLEAR_OVERRIDE_BURSTS", 1
        ):
            commander.update(
                active=True,
                setpoint=None,
                telemetry_status={**telemetry.status(), "fix_mode_active": True},
                now=5.0,
                guidance={"coord_x": 0.0, "coord_y": 0.0, "hold": True},
            )
            mav.calls.clear()
            status = commander.update(
                active=False,
                setpoint=None,
                telemetry_status={**telemetry.status(), "fix_mode_active": True},
                now=5.2,
            )
        self.assertEqual(status["state"], "idle")
        self.assertFalse(status["engaged"])
        self.assertEqual(mav.calls[0][0], "rc_override")
        self.assertEqual(mav.calls[0][1][2], 0)
        self.assertEqual(mav.calls[0][1][3], 0)
        self.assertEqual(mav.calls[1][0], "set_mode")
        self.assertEqual(mav.calls[1][1][2], 5)

    def test_rc_loss_while_acro_sends_rtl(self) -> None:
        telemetry, mav = self._telemetry()
        commander = ApproachCommander(telemetry)
        with patch("config.APPROACH_CONTROL_MODE", "acro"), patch("config.MAVLINK_APPROACH_TX", True), patch(
            "config.FIX_RC_LOSS_RTL_REPEATS", 3
        ), patch("config.FIX_RTL_CLEAR_OVERRIDE_ON_RC_LOSS", False):
            commander.update(
                active=True,
                setpoint=None,
                telemetry_status={**telemetry.status(), "fix_mode_active": True},
                now=5.0,
                guidance={"coord_x": 0.0, "coord_y": 0.0, "hold": False},
            )
            mav.calls.clear()
            lost = dict(telemetry.status())
            lost["rc_link_ok"] = False
            status = commander.update(
                active=True,
                setpoint=None,
                telemetry_status=lost,
                now=6.5,
            )
        self.assertEqual(status["state"], "failsafe")
        self.assertEqual(status["error"], "rc_loss")
        rtl = [call for call in mav.calls if call[0] == "set_mode"]
        self.assertEqual(len(rtl), 3)
        self.assertEqual(rtl[0][1][2], 6)

    def test_px4_uses_offboard_custom_mode(self) -> None:
        self.assertEqual(guided_custom_mode(12), 6 << 16)
        self.assertEqual(guided_custom_mode(3), 4)


if __name__ == "__main__":
    unittest.main()
