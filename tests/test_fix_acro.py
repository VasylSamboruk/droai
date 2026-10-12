from __future__ import annotations

import unittest
from unittest.mock import patch

from fix.fix_acro_control import AcroFixController
from fix.fix_pid import PID
from NEW.visual_approach import frame_coords


class FixPidTests(unittest.TestCase):
    def test_output_is_clamped_and_zero_at_zero_error(self) -> None:
        pid = PID(0.5, 0.0, 0.0, out_max=0.2, i_max=0.1)
        self.assertEqual(pid.update(0.0, 0.05), 0.0)
        self.assertEqual(pid.update(10.0, 0.05), 0.2)
        self.assertEqual(pid.update(-10.0, 0.05), -0.2)


class AcroFixControllerTests(unittest.TestCase):
    def test_copter_uses_yaw_for_horizontal_error(self) -> None:
        controller = AcroFixController()
        with patch("config.APPROACH_ACRO_GEOMETRY", "copter"), patch(
            "config.FIX_ACRO_PWM_SLEW_US_PER_S", 0.0
        ), patch("config.FIX_ACRO_LEVEL_ENABLED", False), patch("config.FIX_ACRO_FORWARD_GAIN", 0.0):
            roll, pitch, yaw, thr, dbg = controller.compute(0.7, 0.0, 0.05, hold=False)
        self.assertEqual(dbg["geometry"], "copter")
        self.assertGreater(yaw, 1500)
        self.assertEqual(roll, 1500)
        self.assertEqual(thr, 1500)

    def test_rocket_uses_roll_for_horizontal_error(self) -> None:
        controller = AcroFixController()
        with patch("config.APPROACH_ACRO_GEOMETRY", "rocket"), patch(
            "config.FIX_ACRO_PWM_SLEW_US_PER_S", 0.0
        ), patch("config.FIX_ACRO_LEVEL_ENABLED", False), patch("config.FIX_ACRO_FORWARD_GAIN", 0.0):
            roll, pitch, yaw, thr, dbg = controller.compute(0.7, 0.0, 0.05, hold=False)
        self.assertEqual(dbg["geometry"], "rocket")
        self.assertGreater(roll, 1500)
        self.assertEqual(yaw, 1500)

    def test_hold_uses_hover_throttle(self) -> None:
        controller = AcroFixController()
        with patch("config.FIX_ACRO_THROTTLE_US", 1700), patch(
            "config.FIX_ACRO_HOLD_THROTTLE_US", 1510
        ), patch("config.FIX_ACRO_PWM_SLEW_US_PER_S", 0.0):
            _, _, _, thr, dbg = controller.compute(0.0, 0.0, 0.05, hold=True)
        self.assertTrue(dbg["hold"])
        self.assertEqual(thr, 1510)

    def test_pitch_compensation_tracks_target_ray_for_fixed_camera(self) -> None:
        controller = AcroFixController()
        frame_size = (1280.0, 720.0)
        with (
            patch("config.APPROACH_PITCH_COMPENSATION_ENABLED", True),
            patch("config.CAMERA_MOUNT_PITCH_DOWN_DEG", 15.0),
            patch("config.FIX_ACRO_TARGET_Y", 0.0),
            patch("config.FIX_ACRO_PWM_SLEW_US_PER_S", 0.0),
            patch("config.FIX_ACRO_LEVEL_ENABLED", False),
            patch("config.FIX_ACRO_FORWARD_GAIN", 0.2),
        ):
            controller.compute(
                0.0, 0.1, 0.05, pitch_deg=0.0, frame_size=frame_size,
                target_key=7, range_error_m=8.0,
            )
            corrected_y = 0.011
            _, _, _, _, visible_dbg = controller.compute(
                0.0, corrected_y, 0.05, pitch_deg=-2.0, frame_size=frame_size,
                target_key=7, range_error_m=8.0,
            )
            _, _, _, _, out_of_view_dbg = controller.compute(
                0.0, corrected_y, 0.05, pitch_deg=-30.0, frame_size=frame_size,
                target_key=7, range_error_m=8.0,
            )

        self.assertTrue(visible_dbg["pitch_compensation_active"])
        self.assertTrue(visible_dbg["target_in_view"])
        self.assertAlmostEqual(visible_dbg["err_y"], 0.0, delta=0.02)
        self.assertFalse(out_of_view_dbg["target_in_view"])
        self.assertEqual(out_of_view_dbg["forward"], 0.0)


class FrameCoordTests(unittest.TestCase):
    def test_box_right_of_center_is_positive_x(self) -> None:
        coord_x, coord_y = frame_coords([960, 300, 1120, 420], (1280, 720))
        self.assertGreater(coord_x, 0.4)
        self.assertLess(abs(coord_y), 0.1)


if __name__ == "__main__":
    unittest.main()
