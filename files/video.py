from __future__ import annotations

import threading
import time
from importlib import import_module
from pathlib import Path
from typing import Any

import cv2
import numpy as np


class VideoSource:
    """Read the configured file or camera in one thread and expose its newest frame."""

    def __init__(
        self,
        source: str | Path | int,
        source_type: str = "file",
        width: int = 1280,
        height: int = 720,
        fps: float = 30.0,
    ) -> None:
        if source_type not in {"file", "webcam", "picamera2"}:
            raise ValueError(f"Unsupported video source: {source_type}")
        self.path = str(source)
        self.source_type = source_type
        self._source = source
        self._requested_width = width
        self._requested_height = height
        self._requested_fps = fps
        self._capture: cv2.VideoCapture | None = None
        self._picamera: Any | None = None
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
        self._started_at = 0.0
        self._last_frame_at: float | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        if self.source_type == "picamera2":
            self._start_picamera2()
        else:
            self._start_capture()

        with self._lock:
            self._latest_frame = None
            self._frame_index = -1
            self._ended = False
            self._error = None
            self._started_at = time.monotonic()
            self._last_frame_at = None
        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(target=self._read_loop, name="video-reader", daemon=True)
        self._thread.start()

    def _start_capture(self) -> None:
        is_live = self.source_type == "webcam"
        source = int(self._source) if is_live else str(self._source)
        if is_live and hasattr(cv2, "CAP_DSHOW"):
            capture = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            if not capture.isOpened():
                capture.release()
                capture = cv2.VideoCapture(source)
        else:
            capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            capture.release()
            raise FileNotFoundError(f"Could not open {self.source_type} source: {self.path}")

        self._capture = capture
        if is_live:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._requested_width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._requested_height)
            capture.set(cv2.CAP_PROP_FPS, self._requested_fps)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._fps = capture.get(cv2.CAP_PROP_FPS) or self._requested_fps
            self._width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or self._requested_width
            self._height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or self._requested_height
        else:
            self._fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
            self._width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def _start_picamera2(self) -> None:
        try:
            Picamera2 = import_module("picamera2").Picamera2
        except (ImportError, AttributeError) as error:
            raise RuntimeError("Picamera2 is available on Raspberry Pi OS, not this PC environment") from error

        camera = Picamera2()
        try:
            camera_config = camera.create_video_configuration(
                main={
                    "size": (self._requested_width, self._requested_height),
                    "format": "RGB888",
                },
                controls={"FrameRate": self._requested_fps},
            )
            camera.configure(camera_config)
            camera.start()
        except Exception:
            camera.close()
            raise

        self._picamera = camera
        self._fps = self._requested_fps
        self._width = self._requested_width
        self._height = self._requested_height

    def _read_loop(self) -> None:
        frame_interval = 1.0 / max(self._fps, 1.0) if self.source_type == "file" else 0.0
        next_frame_at = time.monotonic()

        while not self._stop_event.is_set():
            if self._pause_event.wait(timeout=0.02):
                next_frame_at = time.monotonic()
                continue

            try:
                if self._picamera is not None:
                    frame = self._picamera.capture_array()
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    ok = frame is not None
                else:
                    capture = self._capture
                    if capture is None:
                        break
                    ok, frame = capture.read()
            except Exception as error:
                with self._frame_ready:
                    self._error = f"Camera read failed: {error}"
                    self._ended = True
                    self._frame_ready.notify_all()
                break

            with self._frame_ready:
                if ok:
                    self._latest_frame = frame
                    self._frame_index += 1
                    self._last_frame_at = time.monotonic()
                else:
                    self._ended = True
                    if self.source_type != "file":
                        self._error = f"{self.source_type} stopped producing frames"
                self._frame_ready.notify_all()
            if not ok:
                break

            if frame_interval:
                next_frame_at += frame_interval
                delay = next_frame_at - time.monotonic()
                if delay > 0:
                    self._stop_event.wait(delay)
                else:
                    next_frame_at = time.monotonic()
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
        if self.source_type != "file":
            self.close()
            self.start()
            return

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
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=0.2)
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        if self._picamera is not None:
            self._picamera.stop()
            self._picamera.close()
            self._picamera = None

    @property
    def info(self) -> dict[str, int | float | bool | str | None]:
        with self._lock:
            error = self._error
            if self.source_type != "file" and not error and self._thread and self._thread.is_alive():
                last_frame_at = self._last_frame_at or self._started_at
                if time.monotonic() - last_frame_at > 3.0:
                    error = (
                        f"No frames from {self.source_type} source {self.path} for 3 seconds; "
                        "check camera permission, device index, or whether another app is using it"
                    )
            return {
                "fps": self._fps,
                "width": self._width,
                "height": self._height,
                "source_type": self.source_type,
                "frame_index": self._frame_index,
                "paused": self._pause_event.is_set(),
                "ended": self._ended,
                "error": error,
            }