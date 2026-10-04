from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import cv2

import config
from files.ai import YOLODetector
from files.candidate import CandidateManager
from files.overlay import Overlay
from files.tracker import BoTSORTTracker
from files.utils import FPSCounter
from files.video import VideoSource


class PipelineController:
    def __init__(self) -> None:
        self.source = VideoSource(config.INPUT_VIDEO)
        self._lock = threading.RLock()
        self._jpeg_ready = threading.Condition(self._lock)
        self._wake_worker = threading.Event()
        self._worker: threading.Thread | None = None
        self._shutdown = threading.Event()
        self._restart_requested = threading.Event()
        self._desired_paused = False
        self._jpeg: bytes | None = None
        self._jpeg_version = 0
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
        }
        self.show_candidates = config.SHOW_CANDIDATES
        self.show_confidence = config.SHOW_CONFIDENCE
        self.show_ids = config.SHOW_ID

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
                    self.source = VideoSource(config.INPUT_VIDEO)
                    self._candidates = self._new_candidate_manager()
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
                    except (FileNotFoundError, cv2.error) as error:
                        with self._lock:
                            self._stats["error"] = str(error)
                        self._wake_worker.wait(timeout=1.0)
                        self._wake_worker.clear()
                        continue

                frame, frame_index = self.source.wait_for_frame(last_frame_index, timeout=0.5)
                if frame is None or frame_index == last_frame_index:
                    if self.source.info["ended"]:
                        with self._lock:
                            self._stats["ended"] = True
                        self._wake_worker.wait(timeout=0.25)
                        self._wake_worker.clear()
                    continue

                last_frame_index = frame_index
                candidate_frame_index = self._processed_frame_count
                self._processed_frame_count += 1
                video_fps = self._video_fps.tick()
                detections: list[dict[str, Any]] = []
                candidates: list[dict[str, Any]] = []
                ai_fps = self._ai_fps.value

                with self._lock:
                    ai_enabled = self._stats["ai_enabled"]
                    should_initialize = ai_enabled and self._detector is None

                if should_initialize:
                    try:
                        detector = YOLODetector(config.MODEL_PATH, config.AI_IMAGE_SIZE, config.TARGET_CLASSES)
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
                            self._detector = detector
                            self._tracker = tracker
                            self._stats["model_loaded"] = True
                            self._stats["error"] = None
                    except Exception as error:
                        with self._lock:
                            self._stats["ai_enabled"] = False
                            self._stats["model_loaded"] = False
                            self._stats["error"] = f"AI: {error}"

                with self._lock:
                    detector = self._detector
                    tracker = self._tracker
                    ai_enabled = self._stats["ai_enabled"]

                if ai_enabled and detector is not None and tracker is not None:
                    started_at = time.perf_counter()
                    try:
                        raw_detections = tracker.update(frame)
                        detections, candidates = self._candidates.update(
                            frame,
                            raw_detections,
                            candidate_frame_index,
                            detector.check_crop,
                        )
                        ai_fps = self._ai_fps.tick()
                        with self._lock:
                            self._stats["ai_latency_ms"] = (time.perf_counter() - started_at) * 1000
                    except Exception as error:
                        with self._lock:
                            self._stats["error"] = f"Inference: {error}"

                with self._lock:
                    stats = {
                        "video_fps": video_fps,
                        "ai_fps": ai_fps,
                        "candidate_checks": self._candidates.total_checks,
                        "show_id": self.show_ids,
                        "show_confidence": self.show_confidence,
                    }
                    self._stats.update(
                        video_fps=round(video_fps, 1),
                        ai_fps=round(ai_fps, 1),
                        targets=len(detections),
                        candidates=len(candidates),
                        candidate_checks=self._candidates.total_checks,
                        frame_index=frame_index,
                        paused=self._desired_paused,
                        ended=False,
                    )
                    show_candidates = self.show_candidates

                output = self._overlay.draw(frame, detections, candidates, stats, show_candidates)
                self._save_frame(output, frame_index)
                encoded, buffer = cv2.imencode(".jpg", output, [cv2.IMWRITE_JPEG_QUALITY, 82])
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

    def _save_frame(self, frame: Any, frame_index: int) -> None:
        if not config.SAVE_OUTPUT_VIDEO:
            return
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
            status["paused"] = self._desired_paused
            status["ended"] = bool(self.source.info["ended"])
            status["show_candidates"] = self.show_candidates
            status["show_confidence"] = self.show_confidence
            status["show_ids"] = self.show_ids
            return status

    def get_jpeg(self, previous_version: int, timeout: float = 2.0) -> tuple[bytes | None, int]:
        with self._jpeg_ready:
            self._jpeg_ready.wait_for(lambda: self._jpeg_version > previous_version, timeout=timeout)
            return self._jpeg, self._jpeg_version

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
        with self._lock:
            self._stats["ai_enabled"] = enabled
            if enabled and self._detector is None:
                self._stats["error"] = None
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
        self.source.close()
        self._wake_worker.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=3.0)
