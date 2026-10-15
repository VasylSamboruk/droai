from pathlib import Path

from config_common import PROJECT_ROOT, RPI5_PROFILE

VIDEO_SOURCE = "picamera2" if RPI5_PROFILE else "webcam"
VIDEO_OUTPUT = "vtx"
VTX_DISPLAY = ":0"
WEB_VIEW_MODE = "video" if RPI5_PROFILE else "dashboard"
WEB_HOST = "127.0.0.1"
WEB_PORT = 5000

INPUT_VIDEO = PROJECT_ROOT / "input" / "test.mp4"
OUTPUT_VIDEO = PROJECT_ROOT / "output" / "tracked.mp4"
LOG_DIRECTORY = PROJECT_ROOT / "output" / "logs"
SAVE_OUTPUT_VIDEO = not RPI5_PROFILE
SAVE_CAMERA_OUTPUT_VIDEO = False

# Backward-compatible settings exports; edit the dedicated modules instead.
from config_ai import *  # noqa: E402,F403
from config_mavlink import *  # noqa: E402,F403
