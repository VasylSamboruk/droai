from __future__ import annotations

import threading
import time
from pathlib import Path

import cv2
import numpy as np


class VideoSource:
    """Read a video file in one thread and expose its newest frame."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._capture: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._frame_ready = threading.Condition(self._lock)
        self._capture_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest_frame: np.ndarray | None = None
        self._frame_index = -1
        self._fps = 0.0
        self._width = 0
        self._height = 0
        self._ended = False
        self._error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        capture = cv2.VideoCapture(self.path)
        if not capture.isOpened():
            capture.release()
            raise FileNotFoundError(f"Could not open video: {self.path}")

        self._capture = capture
        self._fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        self._width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._stop_event.clear()
        self._pause_event.clear()
        self._ended = False
        self._error = None
        self._thread = threading.Thread(target=self._read_loop, name="video-reader", daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        frame_interval = 1.0 / max(self._fps, 1.0)
        next_frame_at = time.monotonic()

        while not self._stop_event.is_set():
            if self._pause_event.wait(timeout=0.02):
                next_frame_at = time.monotonic()
                continue

            capture = self._capture
            if capture is None:
                break

            with self._capture_lock:
                ok, frame = capture.read()
                if ok:
                    with self._frame_ready:
                        self._latest_frame = frame
                        self._frame_index += 1
                        self._frame_ready.notify_all()
                else:
                    with self._frame_ready:
                        self._ended = True
                        self._frame_ready.notify_all()
            if not ok:
                break

            next_frame_at += frame_interval
            delay = next_frame_at - time.monotonic()
            if delay > 0:
                self._stop_event.wait(delay)
            else:
                next_frame_at = time.monotonic()

    def get_latest_frame(self) -> tuple[np.ndarray | None, int]:
        with self._lock:
            frame = None if self._latest_frame is None else self._latest_frame.copy()
            return frame, self._frame_index

    def wait_for_frame(self, previous_index: int, timeout: float = 1.0) -> tuple[np.ndarray | None, int]:
        with self._frame_ready:
            self._frame_ready.wait_for(
                lambda: self._frame_index > previous_index or self._ended or self._error is not None,
                timeout=timeout,
            )
            frame = None if self._latest_frame is None else self._latest_frame.copy()
            return frame, self._frame_index

    def pause(self) -> None:
        self._pause_event.set()

    def resume(self) -> None:
        self._pause_event.clear()

    def restart(self) -> None:
        capture = self._capture
        if capture is None or not capture.isOpened():
            self.start()
            return

        self._pause_event.set()
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Video reader did not stop in time to restart")
        with self._capture_lock:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            with self._lock:
                self._latest_frame = None
                self._frame_index = -1
                self._ended = False
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._read_loop, name="video-reader", daemon=True)
        self._thread.start()
        self._pause_event.clear()

    def close(self) -> None:
        self._stop_event.set()
        self._pause_event.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._capture is not None:
            with self._capture_lock:
                self._capture.release()
            self._capture = None

    @property
    def info(self) -> dict[str, int | float | bool | str | None]:
        with self._lock:
            return {
                "fps": self._fps,
                "width": self._width,
                "height": self._height,
                "frame_index": self._frame_index,
                "paused": self._pause_event.is_set(),
                "ended": self._ended,
                "error": self._error,
            }