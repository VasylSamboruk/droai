# Drone AI — тестова версія для ПК

## Автозапуск на Raspberry Pi (після перезавантаження)

Вимкнути:
```bash
mv ~/.config/autostart/drone-ai-vtx.desktop ~/.config/autostart/drone-ai-vtx.desktop.disabled
```

Увімкнути:
```bash
mv ~/.config/autostart/drone-ai-vtx.desktop.disabled ~/.config/autostart/drone-ai-vtx.desktop
```

Після зміни перезавантаж Pi: `sudo reboot`.

Тестовий стенд для розпізнавання та трекінгу транспорту з USB-вебкамери або відеофайлу. Джерело кадрів відокремлене від AI-ядра, щоб пізніше підключити камеру Raspberry Pi без переписування трекінгу.

## Файли та призначення

- `main.py` — запускає PC dashboard або Pi fullscreen VTX/Web output.
- `config.py` — джерело відео, відеовихід і сумісний фасад налаштувань.
- `config_common.py` — профіль Raspberry Pi / ПК.
- `config_ai.py` — модель, роздільність, confidence, частота inference і трекінг.
- `config_mavlink.py` — телеметрія, RC-канали, failsafe та параметри керування.
- `files/video.py` — читання відеофайлу або Picamera2 у latest-frame буфер.
- `files/browser_video.py` — приймає JPEG-кадри з браузерної вебкамери; старі кадри замінюються новими.
- `files/pipeline.py` — видає preview окремо від фонового AI worker.
- `files/ai.py` — YOLO detection і повторна перевірка crop.
- `files/candidate.py` — weak candidates, ROI crop та multi-frame confirmation.
- `files/tracker.py` і `files/botsort.yaml` — BoT-SORT, GMC і track IDs.
- `files/overlay.py` — рамки, класи, IDs, confidence та HUD.
- `files/web.py` — Flask dashboard, control/status API і прийом кадрів від браузера.
- `mavlink/` — приймання MAVLink-телеметрії, RC-канали 8/9 для lock/cycle та окремо керований visual-approach; налаштування і запобіжники — у [mavlink/README.md](mavlink/README.md).
- `templates/index.html`, `static/app.js`, `static/style.css` — сторінка, керування і вигляд dashboard.
- `models/best.pt` — вихідний custom checkpoint; `models/best_ncnn_model/` — оптимізований NCNN export для Pi 5; `models/yolo26n.pt` — старий COCO baseline.
- `input/` — локальні відеофайли; `output/` — локальний запис і runtime tracker config.
- `main_vtx.py` — старий Pi/VTX прототип; його fullscreen output перенесено в `main.py`.
- `requirements.txt` — залежності PC-версії.

У режимі webcam браузер показує камеру напряму через `<video>`; в Python надсилаються лише JPEG-кадри з частотою AI. Canvas накладає отримані рамки на плавне відео. Це дозволяє preview не чекати на YOLO.

## Можливості

- Вибір між відеофайлом, USB-вебкамерою та Picamera2.
- Start/Pause/Restart для відеофайлу, AI та overlay-перемикачі.
- YOLO detection, weak-candidate ROI rechecks і BoT-SORT із sparse optical-flow GMC.
- `TRACKING_STABILITY_ENABLED` у `config_ai.py` вмикає стабільніші ID та плавніші рамки; встанови `False` і перезапусти застосунок, щоб повернути попередні параметри трекінгу й згладжування.
- Поточний тестовий профіль використовує `AI_MODEL = "yolo26n_ncnn"` (`models/yolo26n_ncnn/`). Щоб повернути навчену транспортну модель, вибери `"custom"`.
- Низькі `AI_CONFIDENCE` / `CONFIRMED_CONF` і пороги BoT-SORT дають шанс слабким детекціям потрапити в трек та на екран; це також може збільшити кількість хибних рамок. На Pi слабкі кандидати вимкнені, тому `CONFIRMED_CONF` визначає мінімум для видимої рамки.
- Журнал кожного AI-кадру з часовою міткою, знайденими класами/ID/впевненістю, затримкою та CPU/RAM зберігається в `output/logs/detections.jsonl`. Журнал автоматично обмежується ротацією (10 МБ × до 5 архівів).
- Preview у браузері, FPS, candidate і ROI-recheck лічильники.
- Запис file-відео; запис live-камери вимкнений за замовчуванням.

## Запуск на Windows

Потрібен Python 3.11–3.13 і сумісний PyTorch wheel. У цьому workspace використовується Python 3.13.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```


Вибір моделі задається через `AI_MODEL` у `config_ai.py`: `"custom"` використовує навчену модель (на Pi — NCNN, на ПК — `best.pt`), а `"yolo26n"` — базову модель COCO. Також можна вказати шлях до власного файлу або каталогу моделі. Поточні назви класів custom-моделі перелічені в `TARGET_CLASSES`; якщо змінюєш модель, перевір, що назви там збігаються з класами моделі.

Для донавчання стартуй із потрібного checkpoint, навчай на розмічених датасетах, а потім задай отриманий файл у `AI_MODEL` та вкажи в `TARGET_CLASSES` лише класи, які є в цій моделі.

Ultralytics YOLO поширюється під AGPL-3.0; є окрема Enterprise ліцензія. Перевір умови перед розповсюдженням або комерційним використанням.

Запусти dashboard:

```powershell
python main.py
```

Відкрий <http://127.0.0.1:5000>. Якщо камера, відеофайл або модель недоступні, dashboard покаже помилку в telemetry.

Для повноекранного тесту на ПК із локальним відео запусти в PowerShell:

```powershell
$env:VIDEO_SOURCE = "file"
$env:VIDEO_OUTPUT = "vtx"
python main.py
```

У fullscreen-вікні Q фіксує/відпускає авто з найбільшою впевненістю, T вмикає/вимикає target lock, а Esc завершує показ. Червона рамка йде за зафіксованою ціллю; у верхньому правому куті показується збільшений crop саме цього авто. Останні AI-рамки залишаються доступними між inference-оновленнями, а скидаються при вимкненні AI, помилці inference або restart джерела. Lock використовує ID BoT-SORT та оптичний потік Lucas–Kanade між AI-кадрами; якщо в кадрі немає придатних візуальних ознак, продовження стеження не гарантується.

Для тесту в браузері з повноекранним переглядом:

```powershell
$env:VIDEO_SOURCE = "file"
$env:VIDEO_OUTPUT = "web"
python main.py
```

Відкрий <http://127.0.0.1:5000> і натисни **Fullscreen**. Q фіксує/відпускає авто, W перемикає lock на наступну підтверджену ціль за BoT-SORT ID (із циклічним переходом), T вмикає/вимикає target lock, F вмикає повний екран, Esc виходить із нього. Для W спочатку зафіксуй авто кнопкою Q; перемикання доступне, коли в кадрі є щонайменше дві цілі з track ID. Червона рамка й збільшений inset показують залочену ціль. Ті самі Q/W/T клавіші працюють у fullscreen-вікні OpenCV (режим `vtx`); Esc закриває показ.

Lock є програмним трекінгом у відео. MAVLink прийом увімкнений профілем за замовчуванням; налаштуй `MAVLINK_CONNECTION` у `config_mavlink.py`, щоб читати телеметрію та RC-канали. Канал 8 — утримуваний тумблер lock, канал 9 — натискання для переходу до наступної цілі. `MAVLINK_APPROACH_TX=0` лишає передачу польотних команд вимкненою. Вмикати її (`MAVLINK_APPROACH_TX=1`) можна лише після перевірки конфігурації та режимів автопілота без пропелерів/на стенді; для цього режиму додатково налаштовується підтвердження FIX. Номери каналів і PWM-поріг задаються в `config_mavlink.py`. Деталі й запобіжники — у [mavlink/README.md](mavlink/README.md) та [PROJECT_GUIDE_UA.md](PROJECT_GUIDE_UA.md).

## Джерело та запис

Основні налаштування розділені за призначенням:

- `config_common.py`: `RPI5_PROFILE` — `True` для Raspberry Pi 5, `False` для ПК.
- `config.py`: `VIDEO_SOURCE`, `VIDEO_OUTPUT`, `VTX_DISPLAY`, `WEB_VIEW_MODE`, `WEB_HOST` і `WEB_PORT`.
- `config_ai.py`: `AI_MODEL`, `AI_IMAGE_SIZE`, `AI_CONFIDENCE`, `CAMERA_WIDTH`, `CAMERA_HEIGHT`, `CAMERA_AI_FPS`, пороги та параметри трекера. Менше роздільність/`imgsz` знижує навантаження; більше допомагає малим і далеким цілям.
- `config_mavlink.py`: `MAVLINK_CONNECTION`, RC-канали, перемикачі безпеки й параметри підльоту.

У `VIDEO_SOURCE` можна вибрати:
- `"webcam"` — браузер безпосередньо відкриває USB-вебкамеру; пристрій вибирається у selector на панелі.
- `"file"` — бере файл із `INPUT_VIDEO`; `SAVE_OUTPUT_VIDEO=True` зберігає результат у `output/tracked.mp4`.
- `"picamera2"` використовує камеру Raspberry Pi OS; на Windows цей режим недоступний.

`CAMERA_WIDTH` / `CAMERA_HEIGHT` задають розмір кадру; `CAMERA_FPS` — частоту камери; `CAMERA_AI_FPS` — частоту кадрів для AI. Pi-профіль за замовчуванням використовує 640×360 для камери та `AI_IMAGE_SIZE=416`; підвищуй ці значення для точності на малих цілях, якщо лишається запас CPU. Запис live-відео вимкнений за замовчуванням.

BoT-SORT параметри й `gmc_method: sparseOptFlow` задаються в `files/botsort.yaml`; ReID вимкнений. Pi profile використовує цей самий AI/tracker pipeline та наявний Picamera2 adapter; Pi runtime бере NCNN export.

## Поточні параметри PC

Baseline використовує `imgsz=960`, tracker gates `0.05`, direct confirmation `0.25` і до шести candidate з ROI recheck. Це чутливі PC-налаштування для малих цілей; перевіряй false positives на своїх відео. Якщо AI відстає, latest-frame buffer відкидає застарілі кадри, не накопичуючи затримку.

## Перенесення на Raspberry Pi 5

Профіль Pi та потрібний вивід вибираються прямо у верхньому блоці `config.py`. Для SSH/VS Code залиш `VIDEO_OUTPUT = "web"` і `WEB_VIEW_MODE = "video"`: у браузері буде лише відео на весь екран із FPS та кількістю треків. Щоб перемкнутися на локальний fullscreen для VTX, задай `VIDEO_OUTPUT = "vtx"` і перезапусти застосунок; для обох виходів задай `"both"` (це додає навантаження і потребує локальної графічної сесії). `main_vtx.py` також лише показував fullscreen-вікно — він не налаштовує GPIO або композитний відеосигнал. Якщо аналоговий вихід уже налаштований системою/адаптером, fullscreen-відео буде видно через нього. Pi-профіль за замовчуванням використовує Picamera2, знижені роздільність і частоту AI та не пише MP4.

Перед перенесенням експортуй модель у NCNN на комп'ютері розробки або Pi:

```powershell
python -c "from ultralytics import YOLO; YOLO('models/best.pt').export(format='ncnn', imgsz=640)"
```

Скопіюй на Pi сам проєкт і весь каталог `models/best_ncnn_model/`; Windows `.venv`, локальні `input/` та `output/` копіювати не потрібно. На 64-bit Raspberry Pi OS встанови системні camera bindings та OpenCV через apt, а Python-залежності проєкту — в окреме середовище:

```bash
sudo apt update
sudo apt install python3-venv python3-picamera2 python3-opencv rpicam-apps
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

`--system-site-packages` потрібен, щоб середовище бачило Picamera2 та системні бібліотеки Raspberry Pi OS; pip-пакети проєкту при цьому встановлюються в `.venv`. NCNN є backend моделі, а PyTorch потрібен застосунку для Ultralytics API та BoT-SORT.

Після встановлення відкрий `config.py` і вибери `VIDEO_OUTPUT` та `VIDEO_SOURCE`; модель і AI-параметри налаштовуються у `config_ai.py`. Для запуску достатньо:

```bash
.venv/bin/python main.py
```

Якщо вибрано `VIDEO_OUTPUT = "web"`, відкрий SSH-тунель з клієнтського комп'ютера:

```bash
ssh -L 5000:127.0.0.1:5000 droneaitraf@PI_HOST
```

Заміни `PI_HOST` на hostname або IP Raspberry Pi, а у браузері відкрий <http://127.0.0.1:5000>. У VS Code можна натомість переадресувати порт `5000`. Dashboard за замовчуванням слухає тільки `127.0.0.1` і не відкривається в мережу.

### Автозапуск fullscreen VTX після ввімкнення Pi

Для Pi OS із графічним автологіном у користувача `droneaitraf` додано desktop-autostart файл `~/.config/autostart/drone-ai-vtx.desktop`. Він запускає `start_vtx.sh`, який чекає 8 секунд після старту desktop і запускає `.venv/bin/python main.py`. Переконайся, що в `config.py` встановлено `VIDEO_OUTPUT = "vtx"`. Лог запуску зберігається в `/home/droneaitraf/.local/state/drone-ai-vtx.log`. Для вимкнення автозапуску прибери цей desktop-файл або перейменуй його з розширення `.desktop`.

`both` вмикає JPEG кодування і споживає більше CPU; для польового VTX використовуйте default `vtx`. Сталі FPS і температура залежать від конкретного Pi, охолодження, камери та моделі, тому після перенесення потрібен тривалий тест. NCNN export тут налаштований, але його швидкодію та VTX-підключення потрібно підтвердити на самому Pi й вашому вже налаштованому відеовиході.