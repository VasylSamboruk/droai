import tempfile
import time
import unittest
from pathlib import Path

import cv2
import numpy as np

from files.video import VideoSource


class VideoSourceTests(unittest.TestCase):
    def test_restart_reopens_reader_after_end_of_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            video_path = Path(temporary_directory) / "sample.avi"
            writer = cv2.VideoWriter(
                str(video_path),
                cv2.VideoWriter_fourcc(*"MJPG"),
                15.0,
                (32, 24),
            )
            if not writer.isOpened():
                self.skipTest("MJPG video writer is unavailable")
            for value in (40, 100, 180):
                writer.write(np.full((24, 32, 3), value, dtype=np.uint8))
            writer.release()

            source = VideoSource(video_path)
            try:
                source.start()
                frame, index = source.wait_for_frame(-1, timeout=2.0)
                self.assertIsNotNone(frame)

                deadline = time.monotonic() + 3.0
                while not source.info["ended"] and time.monotonic() < deadline:
                    _, index = source.wait_for_frame(index, timeout=0.5)
                self.assertTrue(source.info["ended"])

                source.restart()
                restarted_frame, restarted_index = source.wait_for_frame(-1, timeout=2.0)
                self.assertIsNotNone(restarted_frame)
                self.assertGreaterEqual(restarted_index, 0)
            finally:
                source.close()


if __name__ == "__main__":
    unittest.main()