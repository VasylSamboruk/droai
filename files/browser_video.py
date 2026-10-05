from __future__ import annotations

import threading
import time
from collections import deque

import cv2
import numpy as np


class BrowserVideoSource:
    """Accept JPEG frames from browser getUserMedia without buffering a backlog."""

    source_type = "webcam"
    path = "browser webcam"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame_ready = threading.Condition(self._lock)
        self._latest_frame: np.ndarray | None = None
        self._frame_index = -1
        self._frame_times: deque[float] = deque(maxlen=60)
        self._width = 0
        self._height = 0
        self._started_at = 0.0
        self._paused = False
        self._closed = True
        self._error: str | None = None

    def start(self) -> None:
        with self._frame_ready:
            self._latest_frame = None
            self._frame_index = -1
            self._frame_times.clear()
            self._started_at = time.monotonic()
            self._paused = False
            self._closed = False
            self._error = None
            self._frame_ready.notify_all()

    def submit_jpeg(self, jpeg_data: bytes) -> bool:
        encoded = np.frombuffer(jpeg_data, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None:
            with self._frame_ready:
                self._error = "Browser sent an invalid JPEG frame"
                self._frame_ready.notify_all()
            return False

        now = time.monotonic()
        with self._frame_ready:
            if self._closed or self._paused:
                return False
            self._latest_frame = frame
            self._frame_index += 1
            self._height, self._width = frame.shape[:2]
            self._frame_times.append(now)
            self._error = None
            self._frame_ready.notify_all()
        return True

    def wait_for_frame(self, previous_index: int, timeout: float = 1.0) -> tuple[np.ndarray | None, int]:
        with self._frame_ready:
            self._frame_ready.wait_for(
                lambda: self._frame_index > previous_index or self._closed or self._error is not None,
                timeout=timeout,
            )
            frame = None if self._latest_frame is None else self._latest_frame.copy()
            return frame, self._frame_index

    def pause(self) -> None:
        with self._frame_ready:
            self._paused = True

    def resume(self) -> None:
        with self._frame_ready:
            self._paused = False

    def restart(self) -> None:
        self.start()

    def close(self) -> None:
        with self._frame_ready:
            self._closed = True
            self._frame_ready.notify_all()

    @property
    def info(self) -> dict[str, int | float | bool | str | None]:
        with self._lock:
            now = time.monotonic()
            timestamps = list(self._frame_times)
            fps = 0.0
            if len(timestamps) > 1 and timestamps[-1] > timestamps[0]:
                fps = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])

            error = self._error
            last_frame_at = timestamps[-1] if timestamps else self._started_at
            if not self._closed and not error and now - last_frame_at > 3.0:
                error = "No browser camera frames received; allow camera access in the browser"

            return {
                "fps": fps,
                "width": self._width,
                "height": self._height,
                "source_type": self.source_type,
                "frame_index": self._frame_index,
                "paused": self._paused,
                "ended": self._closed,
                "error": error,
            }