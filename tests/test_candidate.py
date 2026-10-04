import unittest

import numpy as np

from files.candidate import CandidateManager


class CandidateManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = CandidateManager(
            min_confidence=0.05,
            max_candidate_confidence=0.25,
            confirmed_confidence=0.25,
            crop_confirm_confidence=0.12,
            max_candidates=1,
            check_every=1,
            confirm_checks=2,
            timeout=5.0,
            crop_size=32,
        )
        self.frame = np.zeros((100, 100, 3), dtype=np.uint8)

    def test_candidate_confirms_after_repeated_crop_checks_without_track_id(self) -> None:
        first = {"class": "car", "confidence": 0.12, "box": [10, 10, 30, 30], "track_id": None}
        second = {"class": "car", "confidence": 0.18, "box": [12, 10, 32, 30], "track_id": None}
        checker = lambda crop, size: ("car", 0.72)

        visible, candidates = self.manager.update(self.frame, [first], 1, checker)
        self.assertEqual(visible, [])
        self.assertEqual(len(candidates), 1)

        visible, candidates = self.manager.update(self.frame, [second], 2, checker)
        self.assertEqual(len(visible), 1)
        self.assertEqual(candidates, [])

    def test_candidate_limit_is_enforced(self) -> None:
        detections = [
            {"class": "car", "confidence": 0.12, "box": [5, 5, 20, 20], "track_id": 1},
            {"class": "truck", "confidence": 0.14, "box": [60, 60, 80, 80], "track_id": 2},
        ]
        _, candidates = self.manager.update(self.frame, detections, 1, lambda crop, size: None)
        self.assertEqual(len(candidates), 1)

    def test_weak_detection_confirms_after_repeated_low_score_crop_checks(self) -> None:
        self.manager.check_every = 3
        self.manager.confirm_checks = 3
        detection = {"class": "car", "confidence": 0.08, "box": [10, 10, 30, 30], "track_id": 7}
        visible = []
        candidates = [detection]
        for frame_index in range(7):
            visible, candidates = self.manager.update(
                self.frame,
                [detection],
                frame_index,
                lambda crop, size: ("car", 0.156),
            )

        self.assertEqual(len(visible), 1)
        self.assertEqual(candidates, [])
        self.assertEqual(self.manager.total_checks, 3)


if __name__ == "__main__":
    unittest.main()