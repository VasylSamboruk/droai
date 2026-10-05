import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
RPI5_PROFILE = os.environ.get("DRONE_PROFILE", "pc").casefold() == "pi5"

INPUT_VIDEO = PROJECT_ROOT / "input" / "test.mp4"
OUTPUT_VIDEO = PROJECT_ROOT / "output" / "tracked.mp4"
SAVE_OUTPUT_VIDEO = not RPI5_PROFILE
SAVE_CAMERA_OUTPUT_VIDEO = False
MODEL_PATH = Path(os.environ.get(
	"MODEL_PATH",
	str(PROJECT_ROOT / "models" / ("best_ncnn_model" if RPI5_PROFILE else "best.pt")),
))

VIDEO_SOURCE = os.environ.get("VIDEO_SOURCE", "picamera2" if RPI5_PROFILE else "webcam")
VIDEO_OUTPUT = os.environ.get("VIDEO_OUTPUT", "vtx" if RPI5_PROFILE else "web").casefold()
# VIDEO_SOURCE can be "file", "webcam", or "picamera2".
CAMERA_DEVICE_INDEX = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30
CAMERA_AI_FPS = 5

AI_IMAGE_SIZE = 640 if RPI5_PROFILE else 960
AI_CONFIDENCE = 0.05
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
CONFIRMED_CONF = 0.25
CANDIDATE_CONFIRM_CONF = 0.12
MAX_CANDIDATES = 2 if RPI5_PROFILE else 6
CANDIDATE_IMG_SIZE = 320
CANDIDATE_CHECK_EVERY = 5 if RPI5_PROFILE else 3
CANDIDATE_CONFIRM_CHECKS = 3
CANDIDATE_TIMEOUT = 5.0

TRACKER = "botsort"
TRACK_HIGH_THRESH = 0.05
TRACK_LOW_THRESH = 0.01
TRACK_NEW_THRESH = 0.05
GMC_METHOD = "sparseOptFlow"
REID_ENABLED = False
TRACK_BUFFER = 30

BOX_THICKNESS = 2
BOX_SMOOTHING = 0.70
SHOW_ID = True
SHOW_CONFIDENCE = True
SHOW_FPS = True
SHOW_CANDIDATES = True

WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")
WEB_PORT = 5000
