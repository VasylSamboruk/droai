import unittest
import threading
import time
from unittest.mock import patch

import cv2
import numpy as np

from NEW.target_lock import TargetLock
from NEW.visual_approach import ApproachHoldController
from files.overlay import Overlay
from files.pipeline import PipelineController
from files.web import create_app


class TargetLockTests(unittest.TestCase):
    def test_rc_channel_8_holds_lock_on_and_unlocks_when_released(self) -> None:
        controller = object.__new__(PipelineController)
        controller._lock = threading.RLock()
        controller._target_lock = TargetLock()
        controller._approach = ApproachHoldController()
        controller._rc_lock_switch_active = None
        controller._rc_cycle_switch_active = None
        controller._stats = {
            "ai_enabled": True,
            "rc_target_lock_switch_raw": None,
            "rc_target_cycle_switch_raw": None,
        }
        controller._source_generation = 1
        controller._latest_result_generation = 1
        controller._latest_result_at = time.monotonic()
        controller._latest_detections = [
            {"class": "car", "confidence": 0.91, "box": [20, 20, 80, 60], "track_id": 6}
        ]

        controller._handle_rc_target_lock_switch(1800, 1000)
        self.assertEqual(controller._target_lock.status()["track_id"], 6)
        controller._handle_rc_target_lock_switch(1800, 1000)
        self.assertTrue(controller._target_lock.locked)
        controller._handle_rc_target_lock_switch(1000, 1000)
        self.assertFalse(controller._target_lock.locked)
        controller._handle_rc_target_lock_switch(1800, 1000)
        self.assertTrue(controller._target_lock.locked)

    def test_rc_channel_9_behaves_like_w_and_cycles_only_on_press(self) -> None:
        controller = object.__new__(PipelineController)
        controller._lock = threading.RLock()
        controller._target_lock = TargetLock()
        controller._approach = ApproachHoldController()
        controller._rc_lock_switch_active = None
        controller._rc_cycle_switch_active = None
        controller._stats = {
            "ai_enabled": True,
            "rc_target_lock_switch_raw": None,
            "rc_target_cycle_switch_raw": None,
        }
        controller._source_generation = 1
        controller._latest_result_generation = 1
        controller._latest_result_at = time.monotonic()
        controller._latest_detections = [
            {"class": "car", "confidence": 0.91, "box": [20, 20, 80, 60], "track_id": 6},
            {"class": "bus", "confidence": 0.8, "box": [10, 10, 30, 30], "track_id": 2},
        ]
        controller._target_lock.toggle([controller._latest_detections[0]])

        controller._handle_rc_target_lock_switch(1000, 1800)
        self.assertEqual(controller._target_lock.status()["track_id"], 2)
        controller._handle_rc_target_lock_switch(1000, 1800)
        self.assertEqual(controller._target_lock.status()["track_id"], 2)

        controller._handle_rc_target_lock_switch(1000, 1000)
        controller._handle_rc_target_lock_switch(1000, 1800)
        self.assertEqual(controller._target_lock.status()["track_id"], 6)

    def test_q_locks_latest_ai_detection_when_inference_takes_longer_than_one_second(self) -> None:
        controller = object.__new__(PipelineController)
        controller._lock = threading.RLock()
        controller._target_lock = TargetLock()
        controller._approach = ApproachHoldController()
        controller._source_generation = 1
        controller._latest_result_generation = 1
        controller._latest_result_at = time.monotonic() - 5.0
        controller._latest_detections = [
            {"class": "car", "confidence": 0.91, "box": [20, 20, 80, 60], "track_id": 6}
        ]
        controller._stats = {"ai_enabled": True}

        self.assertTrue(controller.toggle_target_lock())
        self.assertEqual(controller._target_lock.status()["track_id"], 6)

    def test_zoom_inset_uses_locked_target_and_locked_box_is_red(self) -> None:
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[50:110, 50:120] = (0, 255, 0)
        frame[180:240, 250:320] = (255, 0, 255)
        locked = {"class": "car", "confidence": 0.6, "box": [50, 50, 120, 110], "track_id": 3}
        other = {"class": "bus", "confidence": 0.95, "box": [250, 180, 320, 240], "track_id": 8}

        output = Overlay().draw(
            frame,
            [locked, other],
            [],
            {"target_lock_status": {"enabled": True, "locked": True, "track_id": 3}},
            minimal_hud=True,
            target_lock=locked,
        )

        self.assertTrue(np.array_equal(output[50, 60], np.array([0, 0, 255], dtype=np.uint8)))
        self.assertTrue(np.array_equal(output[87, 508], np.array([0, 255, 0], dtype=np.uint8)))
        connector = output[76:94, 150:360]
        self.assertTrue(np.any(
            (connector[:, :, 2] > 180)
            & (connector[:, :, 1] < 80)
            & (connector[:, :, 0] < 80)
        ))

    def test_zoom_remains_visible_with_only_locked_detection(self) -> None:
        frame = np.full((360, 640, 3), (0, 255, 0), dtype=np.uint8)
        locked = {"class": "car", "confidence": 0.7, "box": [50, 50, 120, 110], "track_id": 3}

        output = Overlay().draw(
            frame,
            [],
            [],
            {"target_lock_status": {"enabled": True, "locked": True, "track_id": 3}},
            minimal_hud=True,
            target_lock=locked,
        )

        self.assertTrue(np.array_equal(output[87, 508], np.array([0, 255, 0], dtype=np.uint8)))

    def test_lock_selects_highest_confidence_and_q_toggle_releases_it(self) -> None:
        lock = TargetLock()
        detections = [
            {"class": "car", "confidence": 0.61, "box": [10, 10, 30, 30], "track_id": 3},
            {"class": "bus", "confidence": 0.88, "box": [40, 10, 70, 35], "track_id": 8},
        ]

        self.assertTrue(lock.toggle(detections))
        self.assertEqual(
            lock.status(),
            {"enabled": True, "locked": True, "track_id": 8, "box": [40.0, 10.0, 70.0, 35.0]},
        )
        self.assertFalse(lock.toggle(detections))
        self.assertFalse(lock.locked)

    def test_lock_status_includes_current_box_for_browser_overlay(self) -> None:
        detection = {"class": "car", "confidence": 0.9, "box": [10, 20, 50, 60], "track_id": 4}
        lock = TargetLock()
        lock.toggle([detection])

        self.assertEqual(lock.status()["box"], detection["box"])

    def test_w_cycles_confirmed_targets_by_track_id_and_wraps(self) -> None:
        lock = TargetLock()
        detections = [
            {"class": "car", "confidence": 0.85, "box": [70, 10, 90, 30], "track_id": 7},
            {"class": "bus", "confidence": 0.91, "box": [40, 10, 60, 30], "track_id": 3},
            {"class": "truck", "confidence": 0.95, "box": [10, 10, 30, 30], "track_id": 12},
            {"class": "car", "confidence": 0.99, "box": [90, 10, 110, 30], "track_id": None},
        ]
        lock.toggle([detections[0]])

        self.assertTrue(lock.cycle(detections))
        self.assertEqual(lock.status()["track_id"], 12)
        self.assertTrue(lock.cycle(detections))
        self.assertEqual(lock.status()["track_id"], 3)
        self.assertTrue(lock.cycle(detections))
        self.assertEqual(lock.status()["track_id"], 7)

    def test_w_does_not_cycle_without_active_lock_or_multiple_tracked_targets(self) -> None:
        lock = TargetLock()
        detections = [{"class": "car", "confidence": 0.9, "box": [10, 10, 30, 30], "track_id": 1}]

        self.assertFalse(lock.cycle(detections))
        lock.toggle(detections)
        self.assertFalse(lock.cycle(detections))
        self.assertEqual(lock.status()["track_id"], 1)

    def test_disabling_lock_releases_target_and_prevents_selection(self) -> None:
        lock = TargetLock()
        detection = {"class": "car", "confidence": 0.9, "box": [10, 10, 30, 30], "track_id": 1}
        lock.toggle([detection])

        lock.set_enabled(False)

        self.assertFalse(lock.locked)
        self.assertFalse(lock.toggle([detection]))

    def test_optical_flow_moves_locked_box_with_target(self) -> None:
        rng = np.random.default_rng(4)
        first = np.zeros((140, 180, 3), dtype=np.uint8)
        first[30:80, 40:100] = rng.integers(20, 240, (50, 60, 3), dtype=np.uint8)
        second = cv2.warpAffine(first, np.float32([[1, 0, 7], [0, 1, 4]]), (180, 140))
        detection = {"class": "car", "confidence": 0.9, "box": [40, 30, 100, 80], "track_id": 5}
        lock = TargetLock()
        lock.toggle([detection])

        lock.update(first, [detection], 1)
        tracked = lock.update(second, [detection], 1)

        self.assertIsNotNone(tracked)
        self.assertAlmostEqual(tracked["box"][0], 47, delta=2)
        self.assertAlmostEqual(tracked["box"][1], 34, delta=2)

    def test_lock_releases_when_target_box_fully_leaves_frame(self) -> None:
        frame = np.zeros((140, 180, 3), dtype=np.uint8)
        detection = {"class": "car", "confidence": 0.9, "box": [40, 30, 100, 80], "track_id": 5}
        lock = TargetLock()
        lock.toggle([detection])
        lock.update(frame, [detection], 1)

        def move_box_outside(_gray: np.ndarray) -> bool:
            lock._box = [-80, 30, -20, 80]
            return True

        with patch.object(lock, "_follow_flow", side_effect=move_box_outside):
            tracked = lock.update(frame, [], 1)

        self.assertIsNone(tracked)
        self.assertFalse(lock.locked)

    def test_lock_stays_active_while_target_is_partially_in_frame(self) -> None:
        frame = np.zeros((140, 180, 3), dtype=np.uint8)
        detection = {"class": "car", "confidence": 0.9, "box": [40, 30, 100, 80], "track_id": 5}
        lock = TargetLock()
        lock.toggle([detection])
        lock.update(frame, [detection], 1)

        def move_box_partly_outside(_gray: np.ndarray) -> bool:
            lock._box = [-20, 30, 40, 80]
            return True

        with patch.object(lock, "_follow_flow", side_effect=move_box_partly_outside):
            tracked = lock.update(frame, [], 1)

        self.assertIsNotNone(tracked)
        self.assertTrue(lock.locked)

    def test_matching_detection_prevents_release_after_flow_drift(self) -> None:
        frame = np.zeros((140, 180, 3), dtype=np.uint8)
        detection = {"class": "car", "confidence": 0.9, "box": [40, 30, 100, 80], "track_id": 5}
        lock = TargetLock()
        lock.toggle([detection])
        lock.update(frame, [detection], 1)

        def move_box_outside(_gray: np.ndarray) -> bool:
            lock._box = [-80, 30, -20, 80]
            return True

        with patch.object(lock, "_follow_flow", side_effect=move_box_outside):
            tracked = lock.update(frame, [detection], 2)

        self.assertIsNotNone(tracked)
        self.assertEqual(tracked["box"], detection["box"])
        self.assertTrue(lock.locked)


class WebLockRouteTests(unittest.TestCase):
    class Controller:
        def __init__(self) -> None:
            self.locked = False
            self.enabled = True

        def get_status(self) -> dict[str, object]:
            return {
                "target_lock": {
                    "enabled": self.enabled,
                    "locked": self.locked,
                    "track_id": 12 if self.locked else None,
                }
            }

        def toggle_target_lock(self) -> bool:
            if not self.enabled:
                return False
            self.locked = not self.locked
            return self.locked

        def cycle_target_lock(self) -> bool:
            return self.enabled and self.locked

        def set_target_lock_enabled(self, enabled: bool) -> None:
            self.enabled = enabled
            if not enabled:
                self.locked = False

    def setUp(self) -> None:
        self.controller = self.Controller()
        self.client = create_app(self.controller).test_client()

    def test_target_lock_route_toggles_lock_state(self) -> None:
        locked = self.client.post("/api/control/target-lock")
        unlocked = self.client.post("/api/control/target-lock")

        self.assertEqual(locked.status_code, 200)
        self.assertTrue(locked.json["target_lock"]["locked"])
        self.assertEqual(unlocked.status_code, 200)
        self.assertFalse(unlocked.json["target_lock"]["locked"])

    def test_target_lock_next_route_requires_active_lock(self) -> None:
        unavailable = self.client.post("/api/control/target-lock-next")
        self.client.post("/api/control/target-lock")
        cycled = self.client.post("/api/control/target-lock-next")

        self.assertEqual(unavailable.status_code, 409)
        self.assertEqual(cycled.status_code, 200)
        self.assertTrue(cycled.json["target_lock"]["locked"])

    def test_target_lock_enabled_route_requires_boolean_and_disables_lock(self) -> None:
        self.client.post("/api/control/target-lock")
        invalid = self.client.post(
            "/api/control/target-lock-enabled",
            json={"enabled": "false"},
        )
        disabled = self.client.post(
            "/api/control/target-lock-enabled",
            json={"enabled": False},
        )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(disabled.json["target_lock"]["enabled"])
        self.assertFalse(disabled.json["target_lock"]["locked"])

if __name__ == "__main__":
    unittest.main()
