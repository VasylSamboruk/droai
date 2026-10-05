from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import cv2

import config
from files.ai import YOLODetector
from files.browser_video import BrowserVideoSource
from files.candidate import CandidateManager
from files.overlay import Overlay
from files.tracker import BoTSORTTracker
from files.utils import FPSCounter
from files.video import VideoSource


class PipelineController:
    def __init__(self) -> None:
        if config.VIDEO_OUTPUT not in {"web", "vtx", "both"}:
            raise ValueError(f"Unsupported VIDEO_OUTPUT: {config.VIDEO_OUTPUT}")
        if config.VIDEO_SOURCE == "webcam" and config.VIDEO_OUTPUT == "vtx":
            raise ValueError("The browser webcam source requires VIDEO_OUTPUT='web' or 'both'")
        self.source = self._new_video_source()
        self._lock = threading.RLock()
        self._jpeg_ready = threading.Condition(self._lock)
        self._display_ready = threading.Condition(self._lock)
        self._ai_condition = threading.Condition(self._lock)
        self._wake_worker = threading.Event()
        self._worker: threading.Thread | None = None
        self._ai_worker: threading.Thread | None = None
        self._shutdown = threading.Event()
        self._restart_requested = threading.Event()
        self._desired_paused = False
        self._pending_ai_frame: tuple[int, int, Any] | None = None
        self._source_generation = 0
        self._latest_result_generation = -1
        self._latest_detections: list[dict[str, Any]] = []
        self._latest_candidates: list[dict[str, Any]] = []
        self._latest_result_at = 0.0
        self._latest_result_version = 0
        self._jpeg: bytes | None = None
        self._jpeg_version = 0
        self._display_frame: Any | None = None
        self._display_version = 0
        self._latest_frame_index = -1
        self._processed_frame_count = 0
        self._video_fps = FPSCounter()
        self._ai_fps = FPSCounter()
        self._detector: YOLODetector | None = None
        self._tracker: BoTSORTTracker | None = None
        self._candidates = self._new_candidate_manager()
        self._overlay = Overlay(config.BOX_THICKNESS, config.BOX_SMOOTHING, config.SHOW_FPS)
        self._writer: cv2.VideoWriter | None = None
        self._last_written_index = -1
        self._stats: dict[str, Any] = {
            "running": False,
            "paused": False,
            "ended": False,
            "ai_enabled": True,
            "model_loaded": False,
            "video_fps": 0.0,
            "ai_fps": 0.0,
            "targets": 0,
            "candidates": 0,
            "candidate_checks": 0,
            "frame_index": -1,
            "error": None,
            "model": Path(config.MODEL_PATH).name,
            "tracker": "BoT-SORT",
            "source_type": config.VIDEO_SOURCE,
            "video_output": config.VIDEO_OUTPUT,
        }
        self.show_candidates = config.SHOW_CANDIDATES
        self.show_confidence = config.SHOW_CONFIDENCE
        self.show_ids = config.SHOW_ID

    @staticmethod
    def _new_video_source() -> VideoSource:
        if config.VIDEO_SOURCE == "webcam":
            return BrowserVideoSource()
        source = {
            "file": config.INPUT_VIDEO,
            "picamera2": config.CAMERA_DEVICE_INDEX,
        }.get(config.VIDEO_SOURCE)
        if source is None:
            raise ValueError(f"Unsupported VIDEO_SOURCE: {config.VIDEO_SOURCE}")
        return VideoSource(
            source,
            source_type=config.VIDEO_SOURCE,
            width=config.CAMERA_WIDTH,
            height=config.CAMERA_HEIGHT,
            fps=config.CAMERA_FPS,
        )

    def _new_candidate_manager(self) -> CandidateManager:
        return CandidateManager(
            min_confidence=config.CANDIDATE_MIN_CONF,
            max_candidate_confidence=config.CANDIDATE_MAX_CONF,
            confirmed_confidence=config.CONFIRMED_CONF,
            crop_confirm_confidence=config.CANDIDATE_CONFIRM_CONF,
            max_candidates=config.MAX_CANDIDATES,
            check_every=config.CANDIDATE_CHECK_EVERY,
            confirm_checks=config.CANDIDATE_CONFIRM_CHECKS,
            timeout=config.CANDIDATE_TIMEOUT,
            crop_size=config.CANDIDATE_IMG_SIZE,
        )

    def start(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._shutdown.clear()
            self._ai_worker = threading.Thread(target=self._run_ai, name="drone-ai-inference", daemon=True)
            self._ai_worker.start()
            self._worker = threading.Thread(target=self._run, name="drone-ai-pipeline", daemon=True)
            self._worker.start()

    def _run(self) -> None:
        with self._lock:
            self._stats["running"] = True
        source_started = False
        last_frame_index = -1

        try:
            while not self._shutdown.is_set():
                if self._restart_requested.is_set():
                    self._restart_requested.clear()
                    if source_started:
                        self.source.close()
                    with self._ai_condition:
                        self._source_generation += 1
                        self._pending_ai_frame = None
                        self._latest_detections = []
                        self._latest_candidates = []
                        self._latest_result_at = 0.0
                        self._latest_result_version += 1
                        self._stats.update(targets=0, candidates=0, candidate_checks=0)
                        self._ai_condition.notify_all()
                    self.source = self._new_video_source()
                    self._overlay.reset()
                    if self._writer is not None:
                        self._writer.release()
                        self._writer = None
                    self._last_written_index = -1
                    self._processed_frame_count = 0
                    last_frame_index = -1
                    source_started = False

                if not source_started:
                    try:
                        self.source.start()
                        source_started = True
                        if self._desired_paused:
                            self.source.pause()
                        with self._lock:
                            self._stats["ended"] = False
                            if not (self._stats["error"] or "").startswith("AI:"):
                                self._stats["error"] = None
                    except (FileNotFoundError, RuntimeError, cv2.error) as error:
                        with self._lock:
                            self._stats["error"] = str(error)
                        self._wake_worker.wait(timeout=1.0)
                        self._wake_worker.clear()
                        continue

                frame, frame_index = self.source.wait_for_frame(last_frame_index, timeout=0.5)
                if frame is None or frame_index == last_frame_index:
                    source_error = self.source.info["error"]
                    if source_error:
                        with self._lock:
                            self._stats["error"] = str(source_error)
                    if self.source.info["ended"]:
                        with self._lock:
                            self._stats["ended"] = True
                        self._wake_worker.wait(timeout=0.25)
                        self._wake_worker.clear()
                    continue

                last_frame_index = frame_index
                self._processed_frame_count += 1
                video_fps = self._video_fps.tick()
                with self._ai_condition:
                    generation = self._source_generation
                    if self._stats["ai_enabled"]:
                        self._pending_ai_frame = (generation, frame_index, frame.copy())
                        self._ai_condition.notify()

                    result_is_current = (
                        self._latest_result_generation == generation
                        and time.monotonic() - self._latest_result_at <= 1.0
                    )
                    detections = list(self._latest_detections) if result_is_current else []
                    candidates = list(self._latest_candidates) if result_is_current else []
                    stats = {
                        "video_fps": video_fps,
                        "ai_fps": self._stats["ai_fps"],
                        "candidate_checks": self._stats["candidate_checks"],
                        "show_id": self.show_ids,
                        "show_confidence": self.show_confidence,
                    }
                    self._stats.update(
                        video_fps=round(video_fps, 1),
                        targets=len(detections) if result_is_current else 0,
                        candidates=len(candidates) if result_is_current else 0,
                        frame_index=frame_index,
                        paused=self._desired_paused,
                        ended=False,
                    )
                    show_candidates = self.show_candidates

                output = self._overlay.draw(
                    frame,
                    detections,
                    candidates,
                    stats,
                    show_candidates,
                    minimal_hud=config.VIDEO_OUTPUT in {"vtx", "both"},
                )
                with self._display_ready:
                    self._display_frame = output
                    self._display_version += 1
                    self._display_ready.notify_all()
                if self._record_output_enabled():
                    self._save_frame(output, frame_index)
                if self.source.source_type != "webcam" and config.VIDEO_OUTPUT in {"web", "both"}:
                    encoded, buffer = cv2.imencode(".jpg", output, [cv2.IMWRITE_JPEG_QUALITY, 82])
                else:
                    encoded, buffer = False, None
                if encoded:
                    with self._jpeg_ready:
                        self._jpeg = buffer.tobytes()
                        self._jpeg_version += 1
                        self._jpeg_ready.notify_all()
        finally:
            self.source.close()
            if self._writer is not None:
                self._writer.release()
                self._writer = None
            with self._lock:
                self._stats["running"] = False

    def _run_ai(self) -> None:
        detector: YOLODetector | None = None
        tracker: BoTSORTTracker | None = None
        candidate_manager = self._new_candidate_manager()
        worker_generation = -1
        ai_frame_index = 0

        while not self._shutdown.is_set():
            with self._ai_condition:
                self._ai_condition.wait_for(
                    lambda: self._shutdown.is_set()
                    or (self._pending_ai_frame is not None and self._stats["ai_enabled"]),
                    timeout=0.5,
                )
                if self._shutdown.is_set():
                    return
                if not self._stats["ai_enabled"] or self._pending_ai_frame is None:
                    continue
                generation, frame_index, frame = self._pending_ai_frame
                self._pending_ai_frame = None

            if generation != worker_generation:
                worker_generation = generation
                ai_frame_index = 0
                candidate_manager = self._new_candidate_manager()
                if detector is not None:
                    detector.model.predictor = None
                    tracker = None
                with self._lock:
                    self._candidates = candidate_manager

            try:
                if detector is None:
                    detector = YOLODetector(config.MODEL_PATH, config.AI_IMAGE_SIZE, config.TARGET_CLASSES)
                    with self._lock:
                        self._detector = detector
                        self._stats["model_loaded"] = True

                if tracker is None:
                    tracker = BoTSORTTracker(
                        detector,
                        config.AI_CONFIDENCE,
                        config.AI_IMAGE_SIZE,
                        config.PROJECT_ROOT,
                        {
                            "track_buffer": config.TRACK_BUFFER,
                            "track_high_thresh": config.TRACK_HIGH_THRESH,
                            "track_low_thresh": config.TRACK_LOW_THRESH,
                            "new_track_thresh": config.TRACK_NEW_THRESH,
                            "gmc_method": config.GMC_METHOD,
                            "with_reid": config.REID_ENABLED,
                        },
                    )
                    with self._lock:
                        self._tracker = tracker

                started_at = time.perf_counter()
                raw_detections = tracker.update(frame)
                ai_frame_index += 1
                detections, candidates = candidate_manager.update(
                    frame,
                    raw_detections,
                    ai_frame_index,
                    detector.check_crop,
                )
                ai_fps = self._ai_fps.tick()
                with self._lock:
                    if generation != self._source_generation or not self._stats["ai_enabled"]:
                        continue
                    self._latest_detections = detections
                    self._latest_candidates = candidates
                    self._latest_result_generation = generation
                    self._latest_result_at = time.monotonic()
                    self._latest_result_version += 1
                    self._stats.update(
                        model_loaded=True,
                        ai_fps=round(ai_fps, 1),
                        targets=len(detections),
                        candidates=len(candidates),
                        candidate_checks=candidate_manager.total_checks,
                        ai_latency_ms=(time.perf_counter() - started_at) * 1000,
                        error=None,
                    )
            except Exception as error:
                with self._lock:
                    if generation != self._source_generation:
                        continue
                    if detector is None:
                        self._stats["ai_enabled"] = False
                    self._stats["model_loaded"] = detector is not None
                    self._stats["error"] = f"Inference: {error}"

    def _save_frame(self, frame: Any, frame_index: int) -> None:
        if self._writer is None:
            config.OUTPUT_VIDEO.parent.mkdir(parents=True, exist_ok=True)
            height, width = frame.shape[:2]
            fps = max(float(self.source.info["fps"] or 30.0), 1.0)
            self._writer = cv2.VideoWriter(
                str(config.OUTPUT_VIDEO),
                cv2.VideoWriter_fourcc(*"mp4v"),
                fps,
                (width, height),
            )
            if not self._writer.isOpened():
                self._writer.release()
                self._writer = None
                with self._lock:
                    self._stats["error"] = "Could not create output/tracked.mp4"
                return

        copies = max(1, frame_index - self._last_written_index)
        for _ in range(copies):
            self._writer.write(frame)
        self._last_written_index = frame_index

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            status = dict(self._stats)
            source_info = self.source.info
            status["paused"] = self._desired_paused
            status["ended"] = bool(source_info["ended"])
            status["source_type"] = self.source.source_type
            status["video_output"] = config.VIDEO_OUTPUT
            status["source_label"] = self._source_label()
            status["source_fps"] = source_info["fps"]
            status["source_width"] = source_info["width"]
            status["source_height"] = source_info["height"]
            status["camera_ai_fps"] = config.CAMERA_AI_FPS
            status["camera_width"] = config.CAMERA_WIDTH
            status["camera_height"] = config.CAMERA_HEIGHT
            result_is_current = (
                self._latest_result_generation == self._source_generation
                and time.monotonic() - self._latest_result_at <= 1.0
            )
            status["overlay_boxes"] = (
                [dict(item) for item in self._latest_detections + self._latest_candidates]
                if result_is_current
                else []
            )
            status["recording"] = self._record_output_enabled()
            status["show_candidates"] = self.show_candidates
            status["show_confidence"] = self.show_confidence
            status["show_ids"] = self.show_ids
            return status

    def get_overlay_status(self) -> dict[str, Any]:
        with self._lock:
            result_is_current = (
                self._latest_result_generation == self._source_generation
                and time.monotonic() - self._latest_result_at <= 1.0
            )
            boxes = self._latest_detections + (self._latest_candidates if self.show_candidates else [])
            return {
                "version": self._latest_result_version,
                "boxes": [dict(item) for item in boxes] if result_is_current else [],
                "show_candidates": self.show_candidates,
                "show_confidence": self.show_confidence,
                "show_ids": self.show_ids,
            }

    def _source_label(self) -> str:
        if self.source.source_type == "file":
            return f"FILE / {Path(config.INPUT_VIDEO).name}"
        if self.source.source_type == "webcam":
            return "BROWSER WEBCAM / LOW-LATENCY"
        return "RPI CSI / PICAMERA2"

    def _record_output_enabled(self) -> bool:
        if self.source.source_type == "file":
            return config.SAVE_OUTPUT_VIDEO
        return config.SAVE_CAMERA_OUTPUT_VIDEO

    def get_jpeg(self, previous_version: int, timeout: float = 2.0) -> tuple[bytes | None, int]:
        with self._jpeg_ready:
            self._jpeg_ready.wait_for(lambda: self._jpeg_version > previous_version, timeout=timeout)
            return self._jpeg, self._jpeg_version

    def get_display_frame(self, previous_version: int, timeout: float = 1.0) -> tuple[Any | None, int]:
        with self._display_ready:
            self._display_ready.wait_for(lambda: self._display_version > previous_version, timeout=timeout)
            return self._display_frame, self._display_version

    def submit_browser_frame(self, jpeg_data: bytes) -> bool:
        if not isinstance(self.source, BrowserVideoSource):
            return False
        return self.source.submit_jpeg(jpeg_data)

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._desired_paused = paused
        if paused:
            self.source.pause()
        else:
            self._wake_worker.set()
            try:
                self.source.resume()
            except cv2.error:
                pass

    def restart(self) -> None:
        self._restart_requested.set()
        self._wake_worker.set()

    def set_ai_enabled(self, enabled: bool) -> None:
        with self._ai_condition:
            self._stats["ai_enabled"] = enabled
            if enabled and self._detector is None:
                self._stats["error"] = None
            if not enabled:
                self._pending_ai_frame = None
            self._ai_condition.notify_all()
        self._wake_worker.set()

    def set_overlay(self, **options: bool) -> None:
        with self._lock:
            if "show_candidates" in options:
                self.show_candidates = options["show_candidates"]
            if "show_confidence" in options:
                self.show_confidence = options["show_confidence"]
            if "show_ids" in options:
                self.show_ids = options["show_ids"]

    def close(self) -> None:
        self._shutdown.set()
        with self._ai_condition:
            self._pending_ai_frame = None
            self._ai_condition.notify_all()
        self.source.close()
        self._wake_worker.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=3.0)
        if self._ai_worker and self._ai_worker.is_alive():
            self._ai_worker.join(timeout=3.0)
