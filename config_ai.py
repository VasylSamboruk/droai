from pathlib import Path

from config_common import PROJECT_ROOT, RPI5_PROFILE

# Model and camera inference settings.
AI_MODEL = "yolo26n_ncnn"
_MODEL_OPTIONS = {
    "custom": PROJECT_ROOT / ("models/best_ncnn_model" if RPI5_PROFILE else "models/best.pt"),
    "yolo26n": PROJECT_ROOT / "models/yolo26n.pt",
    "yolo26n_ncnn": PROJECT_ROOT / "models/yolo26n_ncnn_model",
}
_selected_model = Path(AI_MODEL)
MODEL_PATH = _MODEL_OPTIONS.get(AI_MODEL.casefold(), _selected_model)
if AI_MODEL.casefold() not in _MODEL_OPTIONS and not _selected_model.is_absolute():
    MODEL_PATH = PROJECT_ROOT / _selected_model

CAMERA_DEVICE_INDEX = 0
CAMERA_WIDTH = 640 if RPI5_PROFILE else 1280
CAMERA_HEIGHT = 360 if RPI5_PROFILE else 720
CAMERA_FPS = 30
CAMERA_AI_FPS = 5
AI_IMAGE_SIZE = 416 if RPI5_PROFILE else 960
AI_CONFIDENCE = 0.05
AI_CPU_THREADS = 2 if RPI5_PROFILE else 4
OPENCV_NUM_THREADS = 1

TARGET_CLASSES = [
    "Bus",
    "Passenger car",
    "Truck transport",
    "bicycle",
    "bus",
    "car",
    "lorry",
    "military-vehicle",
    "truck",
]

CANDIDATE_MIN_CONF = 0.05
CANDIDATE_MAX_CONF = 0.25
CONFIRMED_CONF = 0.10
CANDIDATE_CONFIRM_CONF = 0.12
MAX_CANDIDATES = 0 if RPI5_PROFILE else 6
CANDIDATE_IMG_SIZE = 320
CANDIDATE_CHECK_EVERY = 8 if RPI5_PROFILE else 3
CANDIDATE_CONFIRM_CHECKS = 3
CANDIDATE_TIMEOUT = 5.0

TRACKER = "botsort"
TRACKING_STABILITY_ENABLED = True
TRACK_HIGH_THRESH = 0.05
TRACK_LOW_THRESH = 0.01
TRACK_NEW_THRESH = 0.05
GMC_METHOD = "none" if RPI5_PROFILE else "sparseOptFlow"
REID_ENABLED = False
TRACK_BUFFER = 60
LOCK_FLOW_SCALE = 0.5

BOX_THICKNESS = 2
BOX_SMOOTHING = 0.75
SHOW_ID = True
SHOW_CONFIDENCE = True
SHOW_FPS = True
SHOW_CANDIDATES = True
WEB_JPEG_QUALITY = 60 if RPI5_PROFILE else 82
