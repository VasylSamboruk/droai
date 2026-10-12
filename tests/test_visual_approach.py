from __future__ import annotations

import math
import unittest

import config
from NEW.visual_approach import (
    MAV_FRAME_BODY_NED,
    POSITION_TARGET_TYPEMASK_VELOCITY_YAW_RATE,
    ApproachHoldController,
    PIDController,
    attitude_target_from_forward_speed,
    body_ned_velocity_target,
    estimate_range_m,
    focal_length_px,
    range_from_area,
)


def box_at_range(
    range_m: float,
    frame_size: tuple[int, int] = (1280, 720),
    class_name: str = "car",
    x_offset_px: float = 0.0,
) -> list[float]:
    frame_width, frame_height = frame_size
    focal_px = focal_length_px(frame_width, config.CAMERA_HFOV_DEG, config.CAMERA_FOCAL_PX)
    width = focal_px * config.TARGET_REAL_WIDTH_M[class_name] / range_m
    height = width * 0.55
    center_x = frame_width * 0.5 + x_offset_px
    center_y = frame_height * 0.5
    return [
        center_x - width * 0.5,
        center_y - height * 0.5,
        center_x + width * 0.5,
        center_y + height * 0.5,
    ]


class VisualApproachTests(unittest.TestCase):
    def test_smaller_box_means_larger_estimated_range(self) -> None:
        near = estimate_range_m(box_at_range(6.0), (1280, 720), "car")
        far = estimate_range_m(box_at_range(18.0), (1280, 720), "car")
        self.assertIsNotNone(near["range_m"])
        self.assertIsNotNone(far["range_m"])
        self.assertAlmostEqual(near["range_m"], 6.0, delta=0.05)
        self.assertAlmostEqual(far["range_m"], 18.0, delta=0.05)
        self.assertGreater(far["range_m"], near["range_m"])
        self.assertGreater(near["box_area_px"], far["box_area_px"])

    def test_area_range_scales_with_inverse_sqrt_area(self) -> None:
        reference_area = 40000.0
        half_linear_area = reference_area / 4.0
        self.assertAlmostEqual(range_from_area(reference_area, reference_area, 10.0), 10.0)
        self.assertAlmostEqual(range_from_area(half_linear_area, reference_area, 10.0), 20.0)

    def test_pid_forward_speed_approaches_standoff_without_overshooting_hard(self) -> None:
        pid = PIDController(kp=0.35, ki=0.02, kd=0.12, i_limit=0.6, output_min=-1.0, output_max=2.0)
        range_m = 20.0
        standoff = 5.0
        dt = 0.05
        min_range = range_m
        for _ in range(400):
            error = range_m - standoff
            vx = 0.0 if abs(error) <= 0.35 else pid.update(error, dt)
            range_m = max(0.0, range_m - vx * dt)
            min_range = min(min_range, range_m)
        self.assertAlmostEqual(range_m, standoff, delta=0.4)
        self.assertGreater(min_range, standoff - 1.25)

    def test_controller_holds_near_standoff_and_builds_body_ned_velocity(self) -> None:
        controller = ApproachHoldController()
        far = controller.update(
            locked=True,
            box=box_at_range(16.0),
            frame_size=(1280, 720),
            class_name="car",
            track_id=4,
            now=1.0,
        )
        self.assertEqual(far["state"], "approach")
        self.assertGreater(far["forward_m_s"], 0.4)
        self.assertEqual(far["setpoint"]["coordinate_frame"], MAV_FRAME_BODY_NED)
        self.assertEqual(far["setpoint"]["type_mask"], POSITION_TARGET_TYPEMASK_VELOCITY_YAW_RATE)
        self.assertEqual(far["setpoint"]["vx"], far["forward_m_s"])

        hold = controller.update(
            locked=True,
            box=box_at_range(config.APPROACH_STANDOFF_M),
            frame_size=(1280, 720),
            class_name="car",
            track_id=4,
            now=1.1,
        )
        self.assertEqual(hold["state"], "hold")
        self.assertEqual(hold["forward_m_s"], 0.0)
        self.assertTrue(hold["hold"])

        too_close = controller.update(
            locked=True,
            box=box_at_range(2.2),
            frame_size=(1280, 720),
            class_name="car",
            track_id=4,
            now=1.2,
        )
        self.assertEqual(too_close["state"], "retreat")
        self.assertLess(too_close["forward_m_s"], 0.0)

    def test_lost_lock_zeros_velocity(self) -> None:
        controller = ApproachHoldController()
        controller.update(
            locked=True,
            box=box_at_range(12.0),
            frame_size=(1280, 720),
            class_name="car",
            track_id=1,
            now=2.0,
        )
        idle = controller.update(
            locked=False,
            box=None,
            frame_size=(1280, 720),
            now=2.1,
        )
        self.assertEqual(idle["state"], "idle")
        self.assertEqual(idle["forward_m_s"], 0.0)
        self.assertEqual(idle["setpoint"]["vx"], 0.0)

    def test_target_to_the_right_requests_positive_body_y(self) -> None:
        controller = ApproachHoldController()
        status = controller.update(
            locked=True,
            box=box_at_range(10.0, x_offset_px=180.0),
            frame_size=(1280, 720),
            class_name="car",
            track_id=9,
            now=3.0,
        )
        self.assertGreater(status["right_m_s"], 0.0)
        self.assertGreater(status["yaw_rate_rad_s"], 0.0)
        self.assertEqual(status["setpoint"]["vy"], status["right_m_s"])

    def test_attitude_target_pitches_down_for_forward_speed(self) -> None:
        target = attitude_target_from_forward_speed(2.0, 2.0, math.radians(8.0))
        self.assertEqual(target["type_mask"], 7)
        self.assertLess(target["pitch_rad"], 0.0)
        self.assertAlmostEqual(target["q"][0], math.cos(target["pitch_rad"] * 0.5), places=6)

    def test_velocity_setpoint_ignores_position(self) -> None:
        setpoint = body_ned_velocity_target(1.25, -0.4, 0.0)
        self.assertEqual(setpoint["x"], 0.0)
        self.assertEqual(setpoint["y"], 0.0)
        self.assertEqual(setpoint["z"], 0.0)
        self.assertEqual(setpoint["vx"], 1.25)
        self.assertEqual(setpoint["vy"], -0.4)


if __name__ == "__main__":
    unittest.main()
