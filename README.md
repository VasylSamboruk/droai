# Drone AI — тестова версія для ПК

Тестовий стенд для розпізнавання та трекінгу транспорту з USB-вебкамери або відеофайлу. Джерело кадрів відокремлене від AI-ядра, щоб пізніше підключити камеру Raspberry Pi без переписування трекінгу.

## Файли та призначення

- `main.py` — запускає PC dashboard або Pi fullscreen VTX/Web output.
- `config.py` — режим та параметри джерела, модель, класи, AI, трекер, overlay і запис.
- `files/video.py` — читання відеофайлу або Picamera2 у latest-frame буфер.
- `files/browser_video.py` — приймає JPEG-кадри з браузерної вебкамери; старі кадри замінюються новими.
- `files/pipeline.py` — видає preview окремо від фонового AI worker.
- `files/ai.py` — YOLO detection і повторна перевірка crop.
- `files/candidate.py` — weak candidates, ROI crop та multi-frame confirmation.
- `files/tracker.py` і `files/botsort.yaml` — BoT-SORT, GMC і track IDs.
- `files/overlay.py` — рамки, класи, IDs, confidence та HUD.
- `files/web.py` — Flask dashboard, control/status API і прийом кадрів від браузера.
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

Активний checkpoint: `models/best.pt`. У ньому є класи `Bus`, `Passenger car`, `Truck transport`, `bicycle`, `bus`, `car`, `lorry`, `military-vehicle` і `truck`; ці класи ввімкнені в `TARGET_CLASSES`. Назви `0`, `1`, `2`, `3` та `object` не ввімкнені, бо з checkpoint metadata незрозуміло, що вони означають. `motorcycle` у списку класів моделі немає. `models/yolo26n.pt` збережено як baseline. Під час запуску застосунок ваги не завантажує.

Для донавчання стартуй із потрібного checkpoint, навчай на розмічених датасетах, а потім задай отриманий файл у `MODEL_PATH` та вкажи в `TARGET_CLASSES` лише класи, які є в цій моделі.

Ultralytics YOLO поширюється під AGPL-3.0; є окрема Enterprise ліцензія. Перевір умови перед розповсюдженням або комерційним використанням.

Запусти dashboard:

```powershell
python main.py
```

Відкрий <http://127.0.0.1:5000>. Якщо камера, відеофайл або модель недоступні, dashboard покаже помилку в telemetry.

## Джерело та запис

У `config.py` задай `VIDEO_SOURCE`:

- `"webcam"` — браузер безпосередньо відкриває USB-вебкамеру; пристрій вибирається у selector на панелі.
- `"file"` — читає `INPUT_VIDEO`; за `SAVE_OUTPUT_VIDEO=True` результат пишеться в `output/tracked.mp4`.
- `"picamera2"` — камера Raspberry Pi OS; на Windows цей режим недоступний.

`CAMERA_WIDTH`, `CAMERA_HEIGHT` задають бажаний розмір, `CAMERA_FPS` — бажану частоту камери, `CAMERA_AI_FPS` — частоту передачі кадрів у Python для AI. `SAVE_CAMERA_OUTPUT_VIDEO=False` залишай для live preview; запис MP4 додає навантаження. `WEB_HOST` за замовчуванням локальний; змінюй його на `0.0.0.0` лише за потреби доступу з мережі.

BoT-SORT параметри й `gmc_method: sparseOptFlow` задаються в `files/botsort.yaml`; ReID вимкнений. Pi profile використовує цей самий AI/tracker pipeline та наявний Picamera2 adapter; Pi runtime бере NCNN export.

## Поточні параметри PC

Baseline використовує `imgsz=960`, tracker gates `0.05`, direct confirmation `0.25` і до шести candidate з ROI recheck. Це чутливі PC-налаштування для малих цілей; перевіряй false positives на своїх відео. Якщо AI відстає, latest-frame buffer відкидає застарілі кадри, не накопичуючи затримку.

## Перенесення на Raspberry Pi 5

Профіль Pi вибирається змінною середовища і не змінює PC defaults. Він використовує Picamera2, 640 px AI input, 5 AI кадрів/с, до двох слабких кандидатів, не пише MP4 і за замовчуванням показує fullscreen VTX-вікно з рамками та мінімальним HUD (`FPS`, `MATCHES`). OpenCV GUI потребує активної X11-сесії Raspberry Pi OS, так само як старий `main_vtx.py`.

Перед перенесенням експортуй модель у NCNN на комп'ютері розробки або Pi:

```powershell
python -c "from ultralytics import YOLO; YOLO('models/best.pt').export(format='ncnn', imgsz=640)"
```

Скопіюй на Pi сам проєкт і весь каталог `models/best_ncnn_model/`; Windows `.venv`, локальні `input/` та `output/` копіювати не потрібно. На Pi потрібні 64-bit Raspberry Pi OS, доступний Picamera2 та OpenCV із GUI підтримкою. Запусти fullscreen output:

```bash
DRONE_PROFILE=pi5 python main.py
```

Для web-only тесту замість fullscreen:

```bash
DRONE_PROFILE=pi5 VIDEO_OUTPUT=web python main.py
```

Для одночасного fullscreen та web тесту на довіреній локальній мережі:

```bash
DRONE_PROFILE=pi5 VIDEO_OUTPUT=both WEB_HOST=0.0.0.0 python main.py
```

`both` вмикає JPEG кодування і споживає більше CPU; для польового VTX використовуйте default `vtx`. Сталі FPS і температура залежать від конкретного Pi, охолодження, камери та моделі, тому після перенесення потрібен тривалий тест. NCNN export тут налаштований, але його швидкодію та VTX-підключення потрібно підтвердити на самому Pi й вашому вже налаштованому відеовиході.