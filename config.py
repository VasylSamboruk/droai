import os
from pathlib import Path

# Корінь проєкту. Не міняй, якщо не переносиш файли.
PROJECT_ROOT = Path(__file__).resolve().parent
# Профіль запуску: "pi5" = Raspberry Pi, будь-що інше = ПК.
RPI5_PROFILE = os.environ.get("DRONE_PROFILE", "pc").casefold() == "pi5"

# --- Відео: звідки читати і куди писати ---
# Вхідний файл, якщо VIDEO_SOURCE = "file".
INPUT_VIDEO = PROJECT_ROOT / "input" / "test.mp4"
# Куди пишеться розмічене відео після обробки файлу.
OUTPUT_VIDEO = PROJECT_ROOT / "output" / "tracked.mp4"
# True = зберігати результат з файлового джерела в OUTPUT_VIDEO. На Pi вимкнено.
SAVE_OUTPUT_VIDEO = not RPI5_PROFILE
# True = писати MP4 і з живої камери (навантаження на CPU). Залиш False для польоту.
SAVE_CAMERA_OUTPUT_VIDEO = False
# Шлях до YOLO-моделі. На Pi — NCNN, на ПК — best.pt. Можна задати MODEL_PATH у середовищі.
MODEL_PATH = Path(os.environ.get(
	"MODEL_PATH",
	str(PROJECT_ROOT / "models" / ("best_ncnn_model" if RPI5_PROFILE else "best.pt")),
))

# Джерело кадрів: "file" | "webcam" | "picamera2".
VIDEO_SOURCE = os.environ.get("VIDEO_SOURCE", "picamera2" if RPI5_PROFILE else "webcam")
# Куди показувати: "web" (браузер), "vtx" (повний екран OpenCV), "both".
VIDEO_OUTPUT = os.environ.get("VIDEO_OUTPUT", "vtx" if RPI5_PROFILE else "web").casefold()
# Індекс USB-камери, якщо колись читаєш її напряму (браузерна webcam цей індекс не бере).
CAMERA_DEVICE_INDEX = 0
# Бажана ширина кадру камери, пікселі.
CAMERA_WIDTH = 1280
# Бажана висота кадру камери, пікселі.
CAMERA_HEIGHT = 720
# Бажана частота камери, кадрів/с. Також dt для PID, якщо кадр затримався.
CAMERA_FPS = 30
# Скільки кадрів/с віддавати в YOLO (менше = менше навантаження).
CAMERA_AI_FPS = 5

# --- AI-розпізнавання ---
# Розмір картинки для YOLO. Більше = точніше і повільніше.
AI_IMAGE_SIZE = 640 if RPI5_PROFILE else 960
# Мінімальна впевненість детекції (0–1). Нижче — більше рамок і шуму.
AI_CONFIDENCE = 0.05
# Які класи з моделі малювати і лочити. Прибери зайве, якщо не треба.
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

# --- Слабкі кандидати (повторна перевірка crop) ---
# Нижня межа впевненості, щоб розглядати об'єкт як кандидата.
CANDIDATE_MIN_CONF = 0.05
# Верхня межа «слабкого» кандидата; вище — вже звичайна детекція.
CANDIDATE_MAX_CONF = 0.25
# Поріг, з якого детекція одразу підтверджена (зелена рамка / трек).
CONFIRMED_CONF = 0.25
# Поріг підтвердження після кількох перевірок crop.
CANDIDATE_CONFIRM_CONF = 0.12
# Скільки слабких кандидатів тримати одночасно.
MAX_CANDIDATES = 2 if RPI5_PROFILE else 6
# Розмір crop для повторної перевірки, пікселі.
CANDIDATE_IMG_SIZE = 320
# Перевіряти кандидата кожен N-й кадр AI.
CANDIDATE_CHECK_EVERY = 5 if RPI5_PROFILE else 3
# Скільки успішних перевірок підряд, щоб підтвердити кандидата.
CANDIDATE_CONFIRM_CHECKS = 3
# Секунди без підтвердження — кандидат зникає.
CANDIDATE_TIMEOUT = 5.0

# --- Трекер BoT-SORT (ID на рамках між кадрами) ---
TRACKER = "botsort"
# Поріг «впевненого» продовження треку.
TRACK_HIGH_THRESH = 0.05
# Поріг слабкого продовження треку.
TRACK_LOW_THRESH = 0.01
# Поріг, щоб завести новий ID.
TRACK_NEW_THRESH = 0.05
# Компенсація руху камери: sparseOptFlow / none / інші методи Ultralytics.
GMC_METHOD = "sparseOptFlow"
# Re-ID зовнішності. False = швидше на слабкому залізі.
REID_ENABLED = False
# Скільки кадрів пам'ятати зниклий трек, перш ніж забути ID.
TRACK_BUFFER = 30

# --- Рамки і HUD на відео ---
# Товщина рамки, пікселі.
BOX_THICKNESS = 2
# Згладжування рамки 0–1. Більше = рамка інертніша, менше дрижить.
BOX_SMOOTHING = 0.70
# Показувати номер треку (#ID).
SHOW_ID = True
# Показувати впевненість моделі на рамці.
SHOW_CONFIDENCE = True
# Показувати FPS у HUD.
SHOW_FPS = True
# Малювати слабких кандидатів (не лише підтверджених).
SHOW_CANDIDATES = True

# --- Веб-панель ---
# Адреса Flask. 127.0.0.1 = лише цей комп. 0.0.0.0 = доступ з мережі.
WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")
# Порт панелі, http://HOST:PORT
WEB_PORT = 5000

# =============================================================================
# MAVLink
# =============================================================================
# Увімкнути прийом телеметрії з борта. Без цього канал 8 у ефірі не читається.
# 1/true = увімкнено. Залиш 0, якщо працюєш без телеметрії.
MAVLINK_ENABLED = os.environ.get("MAVLINK_ENABLED", "0").casefold() in {
	"1", "true", "yes", "on",
}
# Адреса лінка, НЕ номер RC-каналу. Приклад UDP: udpin:0.0.0.0:14550, COM: COM6.
MAVLINK_CONNECTION = os.environ.get("MAVLINK_CONNECTION", "udpin:0.0.0.0:14550")
# Швидкість COM-порта. Для UDP ігнорується.
MAVLINK_BAUD = int(os.environ.get("MAVLINK_BAUD", "57600"))
# Секунди без heartbeat = «нема зв'язку», команди підльоту не шлються.
MAVLINK_HEARTBEAT_TIMEOUT = float(os.environ.get("MAVLINK_HEARTBEAT_TIMEOUT", "3.0"))
# Тумблер lock/автопідліт. Увімкнув = лочить і (якщо TX) летить; вимкнув = стіки тобі.
MAVLINK_TARGET_LOCK_CHANNEL = int(os.environ.get("MAVLINK_TARGET_LOCK_CHANNEL", "8"))
# Тумблер «наступна ціль», як клавіша W. Спрацьовує один раз при вмиканні.
MAVLINK_TARGET_CYCLE_CHANNEL = int(os.environ.get("MAVLINK_TARGET_CYCLE_CHANNEL", "9"))
# PWM вище цього = тумблер увімкнений, на рівні або нижче = вимкнений (мкс).
MAVLINK_RC_SWITCH_THRESHOLD_US = int(os.environ.get("MAVLINK_RC_SWITCH_THRESHOLD_US", "1500"))
# RC-канал, який показує/підтверджує увімкнений FIX. 0 = FIX-режим не визначається.
MAVLINK_FIX_MODE_CHANNEL = int(os.environ.get("MAVLINK_FIX_MODE_CHANNEL", "0"))
# PWM на цьому каналі, який означає FIX увімкнено. 0 = FIX-режим не визначається.
MAVLINK_FIX_MODE_PWM_US = int(os.environ.get("MAVLINK_FIX_MODE_PWM_US", "0"))
# Допуск PWM для визначення FIX, мкс.
MAVLINK_FIX_MODE_PWM_TOLERANCE_US = int(
	os.environ.get("MAVLINK_FIX_MODE_PWM_TOLERANCE_US", "100")
)

# ГОЛОВНИЙ ВИМИКАЧ АВТОПІДЛЬОТУ. False = канал 8 лише лочить рамку, коптер не веде.
# True = при увімкненому 8 бере керування (ACRO override або GUIDED).
# Все інше (AI, lock, телеметрія) працює незалежно від цього.
MAVLINK_APPROACH_TX = os.environ.get("MAVLINK_APPROACH_TX", "1").casefold() in {
	"1", "true", "yes", "on",
}
# Як вести при тумблері 8: "acro" = стіки RC override + PID на рамку (як FIX);
# "guided" = SET_POSITION_TARGET_LOCAL_NED, швидкість у метрах.
APPROACH_CONTROL_MODE = os.environ.get("APPROACH_CONTROL_MODE", "acro").strip().casefold()
# Геометрія ACRO: "copter" = камера вперед (X→yaw, Y→pitch, крен рівняти roll);
# "rocket" = крутий піке як у FIX (X→roll, Y→pitch, крен рівняти yaw).
APPROACH_ACRO_GEOMETRY = os.environ.get("APPROACH_ACRO_GEOMETRY", "copter").strip().casefold()
# Компенсувати зсув цілі у кадрі при нахилі корпусу. Опційно; спершу калібруй на стенді.
APPROACH_PITCH_COMPENSATION_ENABLED = os.environ.get(
	"APPROACH_PITCH_COMPENSATION_ENABLED", "0"
).casefold() in {"1", "true", "yes", "on"}
# Кут камери вниз відносно носа коптера, градуси. Заміри приблизні — перевір перед увімкненням компенсації.
CAMERA_MOUNT_PITCH_DOWN_DEG = float(os.environ.get("CAMERA_MOUNT_PITCH_DOWN_DEG", "15"))
# True = не брати керування і не летіти, поки борт не armed.
MAVLINK_APPROACH_REQUIRE_ARMED = os.environ.get(
	"MAVLINK_APPROACH_REQUIRE_ARMED", "1"
).casefold() in {"1", "true", "yes", "on"}
# Fail-closed: не передавати flight-команди, доки RC_CHANNELS не підтвердить FIX ON.
# Для цього задай MAVLINK_FIX_MODE_CHANNEL і MAVLINK_FIX_MODE_PWM_US.
MAVLINK_APPROACH_REQUIRE_FIX_MODE = os.environ.get(
	"MAVLINK_APPROACH_REQUIRE_FIX_MODE", "1"
).casefold() in {"1", "true", "yes", "on"}
# Скільки разів на секунду слати setpoint. 10 зазвичай досить для GUIDED.
MAVLINK_APPROACH_RATE_HZ = float(os.environ.get("MAVLINK_APPROACH_RATE_HZ", "10"))
# Номер режиму ArduCopter GUIDED. Для PX4 Offboard ставиться сам.
MAVLINK_APPROACH_GUIDED_MODE = int(os.environ.get("MAVLINK_APPROACH_GUIDED_MODE", "4"))
# Куди повернути коптер, якщо попередній режим невідомий (5 = LOITER у ArduCopter).
MAVLINK_APPROACH_HOLD_MODE = int(os.environ.get("MAVLINK_APPROACH_HOLD_MODE", "5"))
# Номер режиму ArduCopter ACRO, куди переходимо в режимі "acro" (типово 2).
MAVLINK_APPROACH_ACRO_MODE = int(os.environ.get("MAVLINK_APPROACH_ACRO_MODE", "2"))
# Скільки каналів слати в RC_CHANNELS_OVERRIDE (8 або 18).
RC_OVERRIDE_CHANNEL_COUNT = int(os.environ.get("RC_OVERRIDE_CHANNEL_COUNT", "8"))
# Який RC-канал (1-based) є roll / pitch / throttle / yaw на польотнику.
OVERRIDE_ROLL_CHANNEL_1_BASED = int(os.environ.get("OVERRIDE_ROLL_CHANNEL_1_BASED", "1"))
OVERRIDE_PITCH_CHANNEL_1_BASED = int(os.environ.get("OVERRIDE_PITCH_CHANNEL_1_BASED", "2"))
OVERRIDE_THROTTLE_CHANNEL_1_BASED = int(os.environ.get("OVERRIDE_THROTTLE_CHANNEL_1_BASED", "3"))
OVERRIDE_YAW_CHANNEL_1_BASED = int(os.environ.get("OVERRIDE_YAW_CHANNEL_1_BASED", "4"))
# Частота ACRO override, Гц. Вище = плавніше, більше навантаження на лінк.
FIX_ACRO_RATE_HZ = float(os.environ.get("FIX_ACRO_RATE_HZ", "20"))
# Газ під час підльоту в ACRO, мкс. 1500 ≈ нейтраль/ховер; більше = сильніше тягне.
FIX_ACRO_THROTTLE_US = float(os.environ.get("FIX_ACRO_THROTTLE_US", "1500"))
# Газ, коли вже на standoff (утримання), мкс.
FIX_ACRO_HOLD_THROTTLE_US = float(os.environ.get("FIX_ACRO_HOLD_THROTTLE_US", "1500"))
# Куди цілити рамку по X: 0 = центр кадру. Праворуч додатне.
FIX_ACRO_TARGET_X = float(os.environ.get("FIX_ACRO_TARGET_X", "0.0"))
# Куди цілити рамку по Y: 0 = центр, 0.05 = трохи нижче центру.
FIX_ACRO_TARGET_Y = float(os.environ.get("FIX_ACRO_TARGET_Y", "0.05"))
# Мертва зона похибки кадру (0–1). Всередині — не крутити стіки.
FIX_ACRO_DEADBAND = float(os.environ.get("FIX_ACRO_DEADBAND", "0.03"))
# Згладжування похибки 0–1. Більше = менше дрижання від трекера.
FIX_ACRO_INPUT_SMOOTH_ALPHA = float(os.environ.get("FIX_ACRO_INPUT_SMOOTH_ALPHA", "0.4"))
# Максимальна зміна PWM за секунду. Менше = м’якші стіки, без ривків.
FIX_ACRO_PWM_SLEW_US_PER_S = float(os.environ.get("FIX_ACRO_PWM_SLEW_US_PER_S", "900"))
# PID наведення по горизонталі кадру (для copter це yaw, для rocket — roll).
FIX_ACRO_ROLL_KP = float(os.environ.get("FIX_ACRO_ROLL_KP", "0.35"))
FIX_ACRO_ROLL_KI = float(os.environ.get("FIX_ACRO_ROLL_KI", "0.05"))
FIX_ACRO_ROLL_KD = float(os.environ.get("FIX_ACRO_ROLL_KD", "0.18"))
FIX_ACRO_ROLL_MAX = float(os.environ.get("FIX_ACRO_ROLL_MAX", "0.5"))
# PID наведення по вертикалі кадру (pitch).
FIX_ACRO_PITCH_KP = float(os.environ.get("FIX_ACRO_PITCH_KP", "0.35"))
FIX_ACRO_PITCH_KI = float(os.environ.get("FIX_ACRO_PITCH_KI", "0.05"))
FIX_ACRO_PITCH_KD = float(os.environ.get("FIX_ACRO_PITCH_KD", "0.18"))
FIX_ACRO_PITCH_MAX = float(os.environ.get("FIX_ACRO_PITCH_MAX", "0.5"))
# Ліміт інтеграла PID, щоб не розкрутило стік.
FIX_ACRO_I_MAX = float(os.environ.get("FIX_ACRO_I_MAX", "0.35"))
# Інверсія осей, якщо дрон крутить не в той бік. 1 або -1.
FIX_ACRO_ROLL_SIGN = float(os.environ.get("FIX_ACRO_ROLL_SIGN", "1.0"))
FIX_ACRO_PITCH_SIGN = float(os.environ.get("FIX_ACRO_PITCH_SIGN", "1.0"))
# М’яка зона біля центру рамки: всередині стік слабший.
FIX_ACRO_SOFT_ZONE = float(os.environ.get("FIX_ACRO_SOFT_ZONE", "0.15"))
FIX_ACRO_SOFT_ZONE_SCALE = float(os.environ.get("FIX_ACRO_SOFT_ZONE_SCALE", "0.3"))
# Вирівнювати горизонт по крену з ATTITUDE. False = не чіпати level-вісь.
FIX_ACRO_LEVEL_ENABLED = os.environ.get("FIX_ACRO_LEVEL_ENABLED", "1").casefold() in {
	"1", "true", "yes", "on",
}
FIX_ACRO_LEVEL_KP = float(os.environ.get("FIX_ACRO_LEVEL_KP", "0.40"))
FIX_ACRO_LEVEL_KI = float(os.environ.get("FIX_ACRO_LEVEL_KI", "0.0"))
FIX_ACRO_LEVEL_KD = float(os.environ.get("FIX_ACRO_LEVEL_KD", "0.10"))
FIX_ACRO_LEVEL_MAX = float(os.environ.get("FIX_ACRO_LEVEL_MAX", "0.35"))
# Не рівняти, якщо крен менший за це, градуси.
FIX_ACRO_LEVEL_DEADBAND_DEG = float(os.environ.get("FIX_ACRO_LEVEL_DEADBAND_DEG", "2.0"))
# На скільки градусів крену вважати похибку «1.0» для PID рівняння.
FIX_ACRO_LEVEL_REF_DEG = float(os.environ.get("FIX_ACRO_LEVEL_REF_DEG", "45.0"))
# Інверсія вирівнювання горизонту. 1 або -1.
FIX_ACRO_LEVEL_SIGN = float(os.environ.get("FIX_ACRO_LEVEL_SIGN", "1.0"))
# Наскільки сильно pitch тягне вперед, коли далеко від standoff (0 = лише наведення).
FIX_ACRO_FORWARD_GAIN = float(os.environ.get("FIX_ACRO_FORWARD_GAIN", "0.35"))
# Дистанція, на якій forward-gain = максимум, метри.
FIX_ACRO_RANGE_REF_M = float(os.environ.get("FIX_ACRO_RANGE_REF_M", "10.0"))
# Знак «вперед» по pitch. Якщо летить назад — постав -1.
FIX_ACRO_PITCH_FORWARD_SIGN = float(os.environ.get("FIX_ACRO_PITCH_FORWARD_SIGN", "1.0"))
# RTL, якщо під час автопідльоту зник RC. False = просто віддати стіки.
FIX_RC_LOSS_FAILSAFE_ENABLED = os.environ.get("FIX_RC_LOSS_FAILSAFE_ENABLED", "1").casefold() in {
	"1", "true", "yes", "on",
}
# Секунди без RC_CHANNELS = втрата пульта.
FIX_RC_LOSS_TIMEOUT_S = float(os.environ.get("FIX_RC_LOSS_TIMEOUT_S", "1.0"))
# Режим failsafe на ArduCopter (6 = RTL).
FIX_FAILSAFE_MODE_ID = int(os.environ.get("FIX_FAILSAFE_MODE_ID", "6"))
# Скільки разів повторити RTL, щоб пакет точно дійшов.
FIX_RC_LOSS_RTL_REPEATS = int(os.environ.get("FIX_RC_LOSS_RTL_REPEATS", "3"))
# True = перед RTL зняти override (65535). False = лишити, як у FIX.
FIX_RTL_CLEAR_OVERRIDE_ON_RC_LOSS = os.environ.get(
	"FIX_RTL_CLEAR_OVERRIDE_ON_RC_LOSS", "0"
).casefold() in {"1", "true", "yes", "on"}
# Скільки пакетів 65535 слати, коли знімаємо override (вимкнений тумблер / RTL).
FIX_RC_LOSS_CLEAR_OVERRIDE_BURSTS = int(os.environ.get("FIX_RC_LOSS_CLEAR_OVERRIDE_BURSTS", "3"))

# =============================================================================
# Автопідліт по рамці (рахунок дистанції і швидкості)
# =============================================================================
# Рахувати дистанцію/PID і показувати RNG на HUD. Не плутати з MAVLINK_APPROACH_TX.
APPROACH_ENABLED = os.environ.get("APPROACH_ENABLED", "1").casefold() in {
	"1", "true", "yes", "on",
}
# На якій дистанції зупинитись і висіти, метри.
APPROACH_STANDOFF_M = float(os.environ.get("APPROACH_STANDOFF_M", "5.0"))
# «Мертва зона» навколо standoff, м. Всередині — швидкість 0, без ривків.
APPROACH_HOLD_DEADBAND_M = float(os.environ.get("APPROACH_HOLD_DEADBAND_M", "0.35"))
# ШВИДКІСТЬ ДО ЦІЛІ, м/с. Це головний регулятор «як швидко летить».
APPROACH_SPEED_M_S = float(os.environ.get("APPROACH_SPEED_M_S", "2.0"))
# Максимум вперед, м/с. За замовчуванням = APPROACH_SPEED_M_S.
APPROACH_MAX_FORWARD_M_S = float(os.environ.get("APPROACH_MAX_FORWARD_M_S", str(APPROACH_SPEED_M_S)))
# Максимум назад, якщо підлетів ближче за standoff, м/с.
APPROACH_MAX_REVERSE_M_S = float(os.environ.get("APPROACH_MAX_REVERSE_M_S", "1.0"))
# Максимальний зсув вправо/вліво, м/с (політ уздовж лінії на ціль).
APPROACH_MAX_LATERAL_M_S = float(os.environ.get("APPROACH_MAX_LATERAL_M_S", str(APPROACH_SPEED_M_S)))
# Наскільки агресивно цілитися вбік по зміщенню рамки (сумісність зі старим кодом).
APPROACH_LATERAL_KP = float(os.environ.get("APPROACH_LATERAL_KP", "1.2"))
# Наскільки швидко розвертати ніс на рамку. Більше = різкіший yaw.
APPROACH_YAW_KP = float(os.environ.get("APPROACH_YAW_KP", "1.4"))
# Ліміт швидкості розвороту, радіан/с.
APPROACH_MAX_YAW_RAD_S = float(os.environ.get("APPROACH_MAX_YAW_RAD_S", "0.8"))
# PID: пропорційна складова. Більше = різкіше газує до цілі.
APPROACH_PID_KP = float(os.environ.get("APPROACH_PID_KP", "0.35"))
# PID: інтеграл. Прибирає залишкову помилку дистанції. Завеликий = розхитування.
APPROACH_PID_KI = float(os.environ.get("APPROACH_PID_KI", "0.02"))
# PID: диференціал. Гасить ривок біля 5 м, щоб не пролетіти ціль.
APPROACH_PID_KD = float(os.environ.get("APPROACH_PID_KD", "0.12"))
# Обмеження інтеграла PID, щоб не «накрутило» швидкість.
APPROACH_PID_I_LIMIT = float(os.environ.get("APPROACH_PID_I_LIMIT", "0.6"))
# Найменша оцінена дистанція, м (захист від божевільних значень рамки).
APPROACH_RANGE_MIN_M = float(os.environ.get("APPROACH_RANGE_MIN_M", "0.8"))
# Найбільша оцінена дистанція, м.
APPROACH_RANGE_MAX_M = float(os.environ.get("APPROACH_RANGE_MAX_M", "120.0"))
# Калібровка площі рамки. 0 = взяти першу pinhole-оцінку після lock як опору.
APPROACH_REFERENCE_RANGE_M = float(os.environ.get("APPROACH_REFERENCE_RANGE_M", "0"))
# Горизонтальний кут огляду камери, градуси. Потрібен для оцінки метрів по рамці.
CAMERA_HFOV_DEG = float(os.environ.get("CAMERA_HFOV_DEG", "70"))
# Фокусна в пікселях. 0 = порахувати з HFOV і ширини кадру. Постав, якщо знаєш точну.
CAMERA_FOCAL_PX = float(os.environ.get("CAMERA_FOCAL_PX", "0"))
# Ширина цілі за замовчуванням, м, якщо класу немає в таблиці нижче.
DEFAULT_TARGET_WIDTH_M = float(os.environ.get("DEFAULT_TARGET_WIDTH_M", "1.8"))
# Реальна ширина класів, м. Від цього рахується дистанція: далі рамка вужча.
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
