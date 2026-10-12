from __future__ import annotations

import unittest
from unittest.mock import patch

import config
from mavlink.telemetry import MAVLinkTelemetry, MESSAGE_TYPES


class FakeMessage:
    def __init__(self, message_type: str, **fields: int | float) -> None:
        self.message_type = message_type
        self.__dict__.update(fields)

    def get_type(self) -> str:
        return self.message_type

    def get_srcSystem(self) -> int:
        return 2

    def get_srcComponent(self) -> int:
        return 1


class FakeConnection:
    def __init__(self, messages: list[FakeMessage | None]) -> None:
        self.messages = messages
        self.request: dict[str, object] | None = None
        self.closed = False

    def recv_match(
        self,
        type: list[str],
        blocking: bool,
        timeout: float,
    ) -> FakeMessage | None:
        self.request = {"type": type, "blocking": blocking, "timeout": timeout}
        return self.messages.pop(0)

    def close(self) -> None:
        self.closed = True


class MAVLinkTelemetryTests(unittest.TestCase):
    def test_connect_and_poll_only_receive_configured_telemetry(self) -> None:
        connection = FakeConnection(
            [
                FakeMessage(
                    "HEARTBEAT",
                    base_mode=128,
                    autopilot=3,
                    type=2,
                    custom_mode=4,
                ),
                FakeMessage(
                    "GLOBAL_POSITION_INT",
                    lat=500000000,
                    lon=300000000,
                    alt=12500,
                    relative_alt=3200,
                    vx=300,
                    vy=400,
                    vz=-100,
                    hdg=9000,
                ),
                FakeMessage(
                    "LOCAL_POSITION_NED",
                    x=1.25,
                    y=-2.5,
                    z=-3.0,
                    vx=0.4,
                    vy=-0.2,
                    vz=0.1,
                ),
                FakeMessage(
                    "SYS_STATUS",
                    voltage_battery=12000,
                    battery_remaining=76,
                ),
            ]
        )
        factory_calls: list[tuple[object, dict[str, object]]] = []

        def factory(connection_string: str, **kwargs: object) -> FakeConnection:
            factory_calls.append((connection_string, kwargs))
            return connection

        telemetry = MAVLinkTelemetry(
            connection_string="udpin:0.0.0.0:14550",
            baud=57600,
            connection_factory=factory,
        )
        telemetry.connect()
        self.assertTrue(telemetry.poll(timeout=0.25))
        self.assertTrue(telemetry.poll(timeout=0.25))
        self.assertTrue(telemetry.poll(timeout=0.25))
        self.assertTrue(telemetry.poll(timeout=0.25))

        status = telemetry.status()
        self.assertEqual(factory_calls, [("udpin:0.0.0.0:14550", {"baud": 57600, "autoreconnect": True})])
        self.assertEqual(connection.request, {"type": list(MESSAGE_TYPES), "blocking": True, "timeout": 0.25})
        self.assertTrue(status["connected"])
        self.assertTrue(status["armed"])
        self.assertEqual(status["custom_mode"], 4)
        self.assertEqual(status["gps"]["latitude_deg"], 50.0)
        self.assertEqual(status["gps"]["longitude_deg"], 30.0)
        self.assertEqual(status["gps"]["altitude_m"], 12.5)
        self.assertEqual(status["velocity"]["ground_speed_m_s"], 5.0)
        self.assertEqual(status["local_position_ned"]["x_m"], 1.25)
        self.assertEqual(status["local_position_ned"]["y_m"], -2.5)
        self.assertEqual(status["local_position_ned"]["z_m"], -3.0)
        self.assertEqual(status["local_position_ned"]["vx_m_s"], 0.4)
        self.assertEqual(status["battery"]["voltage_v"], 12.0)
        self.assertEqual(status["battery"]["remaining_percent"], 76)

        telemetry.close()
        self.assertTrue(connection.closed)

    def test_status_marks_missing_and_stale_heartbeat_disconnected(self) -> None:
        connection = FakeConnection([
            FakeMessage("HEARTBEAT", base_mode=0, autopilot=3, type=2, custom_mode=0)
        ])
        telemetry = MAVLinkTelemetry(
            connection_factory=lambda *_args, **_kwargs: connection
        )
        telemetry.connect()
        with patch("mavlink.telemetry.time.monotonic", return_value=100.0):
            telemetry.poll()
            self.assertTrue(telemetry.status()["connected"])
        with patch("mavlink.telemetry.time.monotonic", return_value=104.0):
            status = telemetry.status()
        self.assertFalse(status["connected"])
        self.assertEqual(status["heartbeat_age_s"], 4.0)

    def test_poll_reads_lock_and_cycle_channels_and_keeps_unavailable_channel(self) -> None:
        connection = FakeConnection([
            FakeMessage("RC_CHANNELS", chan8_raw=1800, chan9_raw=1000, chan10_raw=1750),
            FakeMessage("RC_CHANNELS_RAW", chan8_raw=1000),
            FakeMessage("RC_CHANNELS", chan8_raw=65535, chan9_raw=1800, chan10_raw=1800),
        ])
        telemetry = MAVLinkTelemetry(connection_factory=lambda *_args, **_kwargs: connection)
        telemetry.connect()

        self.assertTrue(telemetry.poll())
        self.assertEqual(telemetry.status()["rc_target_lock_switch_raw"], 1800)
        self.assertEqual(telemetry.status()["rc_target_cycle_switch_raw"], 1000)
        self.assertTrue(telemetry.poll())
        self.assertEqual(telemetry.status()["rc_target_lock_switch_raw"], 1000)
        self.assertEqual(telemetry.status()["rc_target_cycle_switch_raw"], 1000)
        self.assertEqual(telemetry.status()["rc_channels_raw"]["10"], 1750)
        self.assertTrue(telemetry.poll())
        self.assertIsNone(telemetry.status()["rc_target_lock_switch_raw"])
        self.assertEqual(telemetry.status()["rc_target_cycle_switch_raw"], 1800)

        telemetry.close()

    def test_poll_reports_configured_fix_mode_rc_position(self) -> None:
        connection = FakeConnection([
            FakeMessage("RC_CHANNELS", chan8_raw=1000, chan9_raw=1000, chan10_raw=1800),
            FakeMessage("RC_CHANNELS", chan8_raw=1000, chan9_raw=1000, chan10_raw=1500),
        ])
        telemetry = MAVLinkTelemetry(connection_factory=lambda *_args, **_kwargs: connection)
        telemetry.connect()

        with (
            patch.object(config, "MAVLINK_FIX_MODE_CHANNEL", 10),
            patch.object(config, "MAVLINK_FIX_MODE_PWM_US", 1800),
            patch.object(config, "MAVLINK_FIX_MODE_PWM_TOLERANCE_US", 75),
        ):
            self.assertTrue(telemetry.poll())
            self.assertTrue(telemetry.status()["fix_mode_active"])
            self.assertTrue(telemetry.poll())
            self.assertFalse(telemetry.status()["fix_mode_active"])

        telemetry.close()

    def test_fix_mode_becomes_unknown_when_rc_messages_are_stale(self) -> None:
        connection = FakeConnection([
            FakeMessage("RC_CHANNELS", chan10_raw=1800),
        ])
        telemetry = MAVLinkTelemetry(connection_factory=lambda *_args, **_kwargs: connection)
        telemetry.connect()
        with (
            patch.object(config, "MAVLINK_FIX_MODE_CHANNEL", 10),
            patch.object(config, "MAVLINK_FIX_MODE_PWM_US", 1800),
            patch("mavlink.telemetry.time.monotonic", return_value=100.0),
        ):
            telemetry.poll()
            self.assertTrue(telemetry.status()["fix_mode_active"])
        with patch("mavlink.telemetry.time.monotonic", return_value=102.0):
            self.assertIsNone(telemetry.status()["fix_mode_active"])
        telemetry.close()

    def test_poll_requires_connection_and_rejects_invalid_values(self) -> None:
        telemetry = MAVLinkTelemetry(connection_factory=lambda *_args, **_kwargs: None)
        with self.assertRaises(RuntimeError):
            telemetry.poll()
        with self.assertRaises(ValueError):
            MAVLinkTelemetry(connection_string=" ")
        with self.assertRaises(ValueError):
            MAVLinkTelemetry(baud=0)
        with self.assertRaises(ValueError):
            telemetry.poll(timeout=-1)


if __name__ == "__main__":
    unittest.main()
