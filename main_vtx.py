import os
os.environ["DISPLAY"] = ":0"
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["QT_LOGGING_RULES"] = "qt.text.font.*=false;*.warning=false"
os.environ["OMP_NUM_THREADS"] = "1"

import cv2
import time
import numpy as np
from picamera2 import Picamera2
import multiprocessing as mp

from config import Config
from ai_engine import run_ai_process

cv2.setNumThreads(1)
print("=== ЗАПУСК FPV-STREAM: VTX DIRECT OUTPUT (MULTIPROCESSING) ===")

locked_target_id = None 
detected_targets = []
num_matches = 0
session_start_time = 0.0

def draw_laser_target(img, cx, cy, w, h, target_id, cls_name, is_locked=False):
    # Твоя ідеальна функція відмальовки без змін[cite: 4]
    color = (0, 255, 255) if is_locked else (0, 0, 255)
    thick = 2 if is_locked else 1
    cross_size = 15 if is_locked else 10
    
    cv2.line(img, (cx - cross_size, cy), (cx + cross_size, cy), color, thick)
    cv2.line(img, (cx, cy - cross_size), (cx, cy + cross_size), color, thick)
    if is_locked: cv2.circle(img, (cx, cy), 5, (0, 255, 255), -1)

    hw, hh = int(w / 2), int(h / 2)
    x1, y1 = cx - hw, cy - hh
    x2, y2 = cx + hw, cy + hh
    corner_len = min(20 if is_locked else 12, int(min(w, h) / 3))

    cv2.line(img, (x1, y1), (x1 + corner_len, y1), color, thick + 1)
    cv2.line(img, (x1, y1), (x1, y1 + corner_len), color, thick + 1)
    cv2.line(img, (x2, y1), (x2 - corner_len, y1), color, thick + 1)
    cv2.line(img, (x2, y1), (x2, y1 + corner_len), color, thick + 1)
    cv2.line(img, (x1, y2), (x1 + corner_len, y2), color, thick + 1)
    cv2.line(img, (x1, y2), (x1, y2 - corner_len), color, thick + 1)
    cv2.line(img, (x2, y2), (x2 - corner_len, y2), color, thick + 1)
    cv2.line(img, (x2, y2), (x2, y2 - corner_len), color, thick + 1)

    status_str = "[LOCK]" if is_locked else ""
    label = f"LSR-{cls_name.upper()}-0{target_id} {status_str}"
    cv2.putText(img, label, (x1, max(y1 - 8, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.5 if is_locked else 0.4, color, 1, cv2.LINE_AA)

def draw_center_box(img):
    # Залишено без змін[cite: 4]
    if not Config.SHOW_CENTER_BOX: return
    cx_scr, cy_scr = Config.CAMERA_WIDTH // 2, Config.CAMERA_HEIGHT // 2
    w_box, h_box = Config.CENTER_BOX_WIDTH // 2, Config.CENTER_BOX_HEIGHT // 2
    x1, y1 = cx_scr - w_box, cy_scr - h_box
    x2, y2 = cx_scr + w_box, cy_scr + h_box

    cv2.rectangle(img, (x1, y1), (x2, y2), (200, 200, 200), 1)
    cv2.line(img, (cx_scr - 8, cy_scr), (cx_scr + 8, cy_scr), (0, 255, 0), 1)
    cv2.line(img, (cx_scr, cy_scr - 8), (cx_scr, cy_scr + 8), (0, 255, 0), 1)
    cv2.putText(img, "AIM ZONE", (x1 + 5, y1 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 180, 180), 1, cv2.LINE_AA)

def switch_lock(control_queue):
    global locked_target_id, detected_targets
    if not detected_targets:
        locked_target_id = None
    else:
        active_ids = [t[4] for t in detected_targets]
        if locked_target_id is not None:
            current_idx = active_ids.index(locked_target_id) if locked_target_id in active_ids else -1
            next_idx = current_idx + 1
            locked_target_id = None if next_idx >= len(active_ids) else active_ids[next_idx]
        else:
            cx_scr, cy_scr = Config.CAMERA_WIDTH // 2, Config.CAMERA_HEIGHT // 2
            w_box, h_box = Config.CENTER_BOX_WIDTH // 2, Config.CENTER_BOX_HEIGHT // 2
            center_candidates = []
            for t in detected_targets:
                tcx, tcy = t[0], t[1]
                if (cx_scr - w_box <= tcx <= cx_scr + w_box) and (cy_scr - h_box <= tcy <= cy_scr + h_box):
                    center_candidates.append((np.hypot(tcx - cx_scr, tcy - cy_scr), t[4]))
            
            if center_candidates:
                center_candidates.sort(key=lambda x: x[0])
                locked_target_id = center_candidates[0][1]
            else:
                sorted_by_dist = sorted(detected_targets, key=lambda t: np.hypot(t[0] - cx_scr, t[1] - cy_scr))
                locked_target_id = sorted_by_dist[0][4]

    print(f"🎯 ЗАХОПЛЕНО ЦІЛЬ ID: #{locked_target_id}")
    # Повідомляємо AI Engine, яку ціль ми залочили, щоб він увімкнув Hard-Lock
    control_queue.put({"action": "set_lock", "id": locked_target_id})


if __name__ == '__main__':
    # Створюємо черги для спілкування між процесами
    frame_queue = mp.Queue(maxsize=1)
    result_queue = mp.Queue(maxsize=1)
    control_queue = mp.Queue(maxsize=5)

    # Запускаємо ШІ як окремий процес!
    ai_process = mp.Process(target=run_ai_process, args=(frame_queue, result_queue, control_queue), daemon=True)
    ai_process.start()

    picam2 = None
    try:
        picam2 = Picamera2()
        cam_config = picam2.create_video_configuration(
            main={"size": (Config.CAMERA_WIDTH, Config.CAMERA_HEIGHT), "format": "RGB888"}
        )
        picam2.configure(cam_config)
        picam2.start()

        cv2.namedWindow("VTX_HUD", cv2.WINDOW_NORMAL)
        cv2.setWindowProperty("VTX_HUD", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        prev_time = time.time()

        while True:
            frame = picam2.capture_array()
            
            # Відправляємо кадр ШІ-процесу (якщо черга повна, ігноруємо, щоб не гальмувати відео)
            if frame_queue.empty():
                frame_queue.put(frame)

            # Перевіряємо, чи повернув ШІ нові координати
            if not result_queue.empty():
                ai_data = result_queue.get()
                detected_targets = ai_data["targets"]
                num_matches = ai_data["matches"]

            # ==========================================
            # ВІДМАЛЬОВКА (працює на максимальній швидкості)
            # ==========================================
            current_time = time.time()
            fps = 1.0 / (current_time - prev_time) if (current_time - prev_time) > 0 else 0
            prev_time = current_time

            draw_center_box(frame)

            targets_to_draw = []
            if locked_target_id is not None:
                session_start_time = 0.0
                targets_to_draw = [t for t in detected_targets if t[4] == locked_target_id]
            else:
                if not detected_targets:
                    session_start_time = 0.0
                else:
                    if session_start_time == 0.0: session_start_time = current_time
                    allowed_count = int(current_time - session_start_time) + 1
                    targets_to_draw = sorted(detected_targets, key=lambda x: x[4])[:allowed_count]

            for cx, cy, w, h, tid, cls_name in targets_to_draw:
                is_locked = (tid == locked_target_id)
                draw_laser_target(frame, cx, cy, w, h, tid, cls_name, is_locked)

            cv2.putText(frame, f"FPS: {int(fps)}", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
            cv2.putText(frame, f"MATCHES: {num_matches}", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
            
            lock_text = f"LOCK ID: #{locked_target_id}" if locked_target_id else "LOCK ID: NONE (Press Q)"
            lock_color = (0, 255, 255) if locked_target_id else (180, 180, 180)
            cv2.putText(frame, lock_text, (15, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, lock_color, 1, cv2.LINE_AA)

            cv2.imshow("VTX_HUD", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == ord('Q'):
                switch_lock(control_queue)  # Передаємо чергу керування
            elif key == 27:
                break

    except Exception as e:
        print(f"❌ Помилка запуска: {e}")
    finally:
        if picam2: picam2.stop()
        cv2.destroyAllWindows()
        if ai_process.is_alive(): ai_process.terminate()
