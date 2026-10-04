# Drone AI — PC Test Bench

PC-first test version of the drone traffic perception pipeline. The frame source is isolated in `files/video.py`; detection, candidate confirmation, tracking, and overlays consume frames without depending on how they were captured. That boundary is intended to make the later Raspberry Pi camera adapter a source replacement, not an AI rewrite.

## What is included

- Local video-file playback with Start, Pause, and Restart controls.
- YOLO detection for configured vehicle classes.
- Weak-candidate ROI rechecks with a configurable candidate limit.
- BoT-SORT tracking with sparse optical-flow GMC and ReID disabled.
- MJPEG browser preview and optional annotated MP4 recording.
- AI and overlay toggles with live FPS and target counts.

## Setup on Windows

Python 3.11–3.13 are supported when a matching PyTorch wheel is available. This workspace currently uses Python 3.13.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The project includes the official pretrained `models/yolo26n.pt` checkpoint for a baseline test. Its COCO classes include `car`, `truck`, `bus`, and `motorcycle`, but not a separate `van` class. Put test clips in `input/`; `input/test.mp4` is the default source. The app does not download weights at startup.

For a later fine-tune, start from `models/yolo26n.pt`, train on your labeled datasets, then set `MODEL_PATH` in `config.py` to the resulting checkpoint and list only class names that exist in that model under `TARGET_CLASSES`.

Ultralytics distributes YOLO under AGPL-3.0, with a separate Enterprise license available. Check the license terms before redistributing or using the model in a commercial product.

Start the local dashboard:

```powershell
python main.py
```

Open <http://127.0.0.1:5000>. The dashboard remains available if the video or model is missing and reports the issue in the telemetry panel. Output is written to `output/tracked.mp4` when a video source is available.

## Configuration

Change paths, target classes, confidence thresholds, candidate limits, tracker settings, display defaults, and web binding in `config.py`. `WEB_HOST` defaults to `127.0.0.1`; change it to `0.0.0.0` only when you intentionally need access from another device on your network.

BoT-SORT parameters and `gmc_method: sparseOptFlow` are in `files/botsort.yaml`. ReID is disabled. The Pi version can reuse `ai.py`, `candidate.py`, `tracker.py`, `overlay.py`, `utils.py`, `pipeline.py`, and the web assets, while replacing `VideoSource` with a Picamera2 source and using an exported NCNN model.

## Current scope

The PC baseline uses `imgsz=960`, `track_high_thresh: 0.05`, `new_track_thresh: 0.05`, and a `0.25` direct-confirmation threshold so small aerial detections reach the candidate system. The larger image size costs more inference time than 640. Up to six candidates are checked by repeated ROI inference; these are intentionally more permissive settings than the later Pi profile. Review false positives on your footage before treating tracks as reliable. The dashboard shows the cumulative ROI recheck count. Recording follows source frame indices and duplicates the latest processed frame when inference skips input frames, preserving approximate source duration.