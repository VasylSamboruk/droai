import os

from config_common import RPI5_PROFILE

MAVLINK_ENABLED = os.environ.get("MAVLINK_ENABLED", "1").casefold() in {"1", "true", "yes", "on"}
_MAVLINK_CONNECTION_DEFAULT = "/dev/ttyAMA0" if RPI5_PROFILE else "udpin:0.0.0.0:14550"
MAVLINK_CONNECTION = os.environ.get("MAVLINK_CONNECTION", _MAVLINK_CONNECTION_DEFAULT)
MAVLINK_BAUD = int(os.environ.get("MAVLINK_BAUD", "57600"))
MAVLINK_HEARTBEAT_TIMEOUT = float(os.environ.get("MAVLINK_HEARTBEAT_TIMEOUT", "3.0"))
MAVLINK_TARGET_LOCK_CHANNEL = int(os.environ.get("MAVLINK_TARGET_LOCK_CHANNEL", "8"))
MAVLINK_TARGET_CYCLE_CHANNEL = int(os.environ.get("MAVLINK_TARGET_CYCLE_CHANNEL", "9"))
MAVLINK_RC_SWITCH_THRESHOLD_US = int(os.environ.get("MAVLINK_RC_SWITCH_THRESHOLD_US", "1500"))
# Zero reuses the target-lock channel; zero PWM uses the switch threshold above.
MAVLINK_FIX_MODE_CHANNEL = int(os.environ.get("MAVLINK_FIX_MODE_CHANNEL", "0"))
MAVLINK_FIX_MODE_PWM_US = int(os.environ.get("MAVLINK_FIX_MODE_PWM_US", "0"))
MAVLINK_FIX_MODE_PWM_TOLERANCE_US = int(os.environ.get("MAVLINK_FIX_MODE_PWM_TOLERANCE_US", "100"))

MAVLINK_APPROACH_TX = os.environ.get("MAVLINK_APPROACH_TX", "0").casefold() in {"1", "true", "yes", "on"}
APPROACH_CONTROL_MODE = os.environ.get("APPROACH_CONTROL_MODE", "acro").strip().casefold()
APPROACH_ACRO_GEOMETRY = os.environ.get("APPROACH_ACRO_GEOMETRY", "copter").strip().casefold()
APPROACH_PITCH_COMPENSATION_ENABLED = os.environ.get("APPROACH_PITCH_COMPENSATION_ENABLED", "0").casefold() in {"1", "true", "yes", "on"}
CAMERA_MOUNT_PITCH_DOWN_DEG = float(os.environ.get("CAMERA_MOUNT_PITCH_DOWN_DEG", "15"))
MAVLINK_APPROACH_REQUIRE_ARMED = os.environ.get("MAVLINK_APPROACH_REQUIRE_ARMED", "1").casefold() in {"1", "true", "yes", "on"}
MAVLINK_APPROACH_REQUIRE_FIX_MODE = os.environ.get("MAVLINK_APPROACH_REQUIRE_FIX_MODE", "1").casefold() in {"1", "true", "yes", "on"}
MAVLINK_APPROACH_RATE_HZ = float(os.environ.get("MAVLINK_APPROACH_RATE_HZ", "10"))
MAVLINK_APPROACH_GUIDED_MODE = int(os.environ.get("MAVLINK_APPROACH_GUIDED_MODE", "4"))
MAVLINK_APPROACH_HOLD_MODE = int(os.environ.get("MAVLINK_APPROACH_HOLD_MODE", "5"))
MAVLINK_APPROACH_ACRO_MODE = int(os.environ.get("MAVLINK_APPROACH_ACRO_MODE", "2"))
RC_OVERRIDE_CHANNEL_COUNT = int(os.environ.get("RC_OVERRIDE_CHANNEL_COUNT", "8"))
OVERRIDE_ROLL_CHANNEL_1_BASED = int(os.environ.get("OVERRIDE_ROLL_CHANNEL_1_BASED", "1"))
OVERRIDE_PITCH_CHANNEL_1_BASED = int(os.environ.get("OVERRIDE_PITCH_CHANNEL_1_BASED", "2"))
OVERRIDE_THROTTLE_CHANNEL_1_BASED = int(os.environ.get("OVERRIDE_THROTTLE_CHANNEL_1_BASED", "3"))
OVERRIDE_YAW_CHANNEL_1_BASED = int(os.environ.get("OVERRIDE_YAW_CHANNEL_1_BASED", "4"))

FIX_ACRO_RATE_HZ = float(os.environ.get("FIX_ACRO_RATE_HZ", "20"))
FIX_ACRO_THROTTLE_US = float(os.environ.get("FIX_ACRO_THROTTLE_US", "1500"))
FIX_ACRO_HOLD_THROTTLE_US = float(os.environ.get("FIX_ACRO_HOLD_THROTTLE_US", "1500"))
FIX_ACRO_TARGET_X = float(os.environ.get("FIX_ACRO_TARGET_X", "0.0"))
FIX_ACRO_TARGET_Y = float(os.environ.get("FIX_ACRO_TARGET_Y", "0.05"))
FIX_ACRO_DEADBAND = float(os.environ.get("FIX_ACRO_DEADBAND", "0.03"))
FIX_ACRO_INPUT_SMOOTH_ALPHA = float(os.environ.get("FIX_ACRO_INPUT_SMOOTH_ALPHA", "0.4"))
FIX_ACRO_PWM_SLEW_US_PER_S = float(os.environ.get("FIX_ACRO_PWM_SLEW_US_PER_S", "900"))
FIX_ACRO_ROLL_KP = float(os.environ.get("FIX_ACRO_ROLL_KP", "0.35"))
FIX_ACRO_ROLL_KI = float(os.environ.get("FIX_ACRO_ROLL_KI", "0.05"))
FIX_ACRO_ROLL_KD = float(os.environ.get("FIX_ACRO_ROLL_KD", "0.18"))
FIX_ACRO_ROLL_MAX = float(os.environ.get("FIX_ACRO_ROLL_MAX", "0.5"))
FIX_ACRO_PITCH_KP = float(os.environ.get("FIX_ACRO_PITCH_KP", "0.35"))
FIX_ACRO_PITCH_KI = float(os.environ.get("FIX_ACRO_PITCH_KI", "0.05"))
FIX_ACRO_PITCH_KD = float(os.environ.get("FIX_ACRO_PITCH_KD", "0.18"))
FIX_ACRO_PITCH_MAX = float(os.environ.get("FIX_ACRO_PITCH_MAX", "0.5"))
FIX_ACRO_I_MAX = float(os.environ.get("FIX_ACRO_I_MAX", "0.35"))
FIX_ACRO_ROLL_SIGN = float(os.environ.get("FIX_ACRO_ROLL_SIGN", "1.0"))
FIX_ACRO_PITCH_SIGN = float(os.environ.get("FIX_ACRO_PITCH_SIGN", "1.0"))
FIX_ACRO_SOFT_ZONE = float(os.environ.get("FIX_ACRO_SOFT_ZONE", "0.15"))
FIX_ACRO_SOFT_ZONE_SCALE = float(os.environ.get("FIX_ACRO_SOFT_ZONE_SCALE", "0.3"))
FIX_ACRO_LEVEL_ENABLED = os.environ.get("FIX_ACRO_LEVEL_ENABLED", "1").casefold() in {"1", "true", "yes", "on"}
FIX_ACRO_LEVEL_KP = float(os.environ.get("FIX_ACRO_LEVEL_KP", "0.40"))
FIX_ACRO_LEVEL_KI = float(os.environ.get("FIX_ACRO_LEVEL_KI", "0.0"))
FIX_ACRO_LEVEL_KD = float(os.environ.get("FIX_ACRO_LEVEL_KD", "0.10"))
FIX_ACRO_LEVEL_MAX = float(os.environ.get("FIX_ACRO_LEVEL_MAX", "0.35"))
FIX_ACRO_LEVEL_DEADBAND_DEG = float(os.environ.get("FIX_ACRO_LEVEL_DEADBAND_DEG", "2.0"))
FIX_ACRO_LEVEL_REF_DEG = float(os.environ.get("FIX_ACRO_LEVEL_REF_DEG", "45.0"))
FIX_ACRO_LEVEL_SIGN = float(os.environ.get("FIX_ACRO_LEVEL_SIGN", "1.0"))
FIX_ACRO_FORWARD_GAIN = float(os.environ.get("FIX_ACRO_FORWARD_GAIN", "0.35"))
FIX_ACRO_RANGE_REF_M = float(os.environ.get("FIX_ACRO_RANGE_REF_M", "10.0"))
FIX_ACRO_PITCH_FORWARD_SIGN = float(os.environ.get("FIX_ACRO_PITCH_FORWARD_SIGN", "1.0"))

FIX_RC_LOSS_FAILSAFE_ENABLED = os.environ.get("FIX_RC_LOSS_FAILSAFE_ENABLED", "1").casefold() in {"1", "true", "yes", "on"}
FIX_RC_LOSS_TIMEOUT_S = float(os.environ.get("FIX_RC_LOSS_TIMEOUT_S", "1.0"))
FIX_FAILSAFE_MODE_ID = int(os.environ.get("FIX_FAILSAFE_MODE_ID", "6"))
FIX_RC_LOSS_RTL_REPEATS = int(os.environ.get("FIX_RC_LOSS_RTL_REPEATS", "3"))
FIX_RTL_CLEAR_OVERRIDE_ON_RC_LOSS = os.environ.get("FIX_RTL_CLEAR_OVERRIDE_ON_RC_LOSS", "0").casefold() in {"1", "true", "yes", "on"}
FIX_RC_LOSS_CLEAR_OVERRIDE_BURSTS = int(os.environ.get("FIX_RC_LOSS_CLEAR_OVERRIDE_BURSTS", "3"))

APPROACH_ENABLED = os.environ.get("APPROACH_ENABLED", "1").casefold() in {"1", "true", "yes", "on"}
APPROACH_STANDOFF_M = float(os.environ.get("APPROACH_STANDOFF_M", "5.0"))
APPROACH_HOLD_DEADBAND_M = float(os.environ.get("APPROACH_HOLD_DEADBAND_M", "0.35"))
APPROACH_SPEED_M_S = float(os.environ.get("APPROACH_SPEED_M_S", "2.0"))
APPROACH_MAX_FORWARD_M_S = float(os.environ.get("APPROACH_MAX_FORWARD_M_S", str(APPROACH_SPEED_M_S)))
APPROACH_MAX_REVERSE_M_S = float(os.environ.get("APPROACH_MAX_REVERSE_M_S", "1.0"))
APPROACH_MAX_LATERAL_M_S = float(os.environ.get("APPROACH_MAX_LATERAL_M_S", str(APPROACH_SPEED_M_S)))
APPROACH_LATERAL_KP = float(os.environ.get("APPROACH_LATERAL_KP", "1.2"))
APPROACH_YAW_KP = float(os.environ.get("APPROACH_YAW_KP", "1.4"))
APPROACH_MAX_YAW_RAD_S = float(os.environ.get("APPROACH_MAX_YAW_RAD_S", "0.8"))
APPROACH_PID_KP = float(os.environ.get("APPROACH_PID_KP", "0.35"))
APPROACH_PID_KI = float(os.environ.get("APPROACH_PID_KI", "0.02"))
APPROACH_PID_KD = float(os.environ.get("APPROACH_PID_KD", "0.12"))
APPROACH_PID_I_LIMIT = float(os.environ.get("APPROACH_PID_I_LIMIT", "0.6"))
APPROACH_RANGE_MIN_M = float(os.environ.get("APPROACH_RANGE_MIN_M", "0.8"))
APPROACH_RANGE_MAX_M = float(os.environ.get("APPROACH_RANGE_MAX_M", "120.0"))
APPROACH_REFERENCE_RANGE_M = float(os.environ.get("APPROACH_REFERENCE_RANGE_M", "0"))
CAMERA_HFOV_DEG = float(os.environ.get("CAMERA_HFOV_DEG", "70"))
CAMERA_FOCAL_PX = float(os.environ.get("CAMERA_FOCAL_PX", "0"))
DEFAULT_TARGET_WIDTH_M = float(os.environ.get("DEFAULT_TARGET_WIDTH_M", "1.8"))
TARGET_REAL_WIDTH_M = {
    "Bus": 2.55,
    "Passenger car": 1.80,
    "Truck transport": 2.50,
    "bicycle": 0.70,
    "bus": 2.55,
    "car": 1.80,
    "lorry": 2.50,
    "military-vehicle": 2.50,
    "truck": 2.50,
}
