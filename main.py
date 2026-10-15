import atexit
import os
import threading

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import config

if config.VIDEO_OUTPUT in {"vtx", "both"}:
    # Set the local X session before importing OpenCV's Qt backend.
    os.environ["DISPLAY"] = config.VTX_DISPLAY
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    os.environ.setdefault("QT_LOGGING_RULES", "qt.text.font.*=false;*.warning=false")

import cv2
from werkzeug.serving import make_server

from files.pipeline import PipelineController
from files.web import create_app


def show_vtx_output(controller: PipelineController) -> None:
    window_name = "Drone AI VTX"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    frame_version = -1
    try:
        while True:
            frame, frame_version = controller.get_display_frame(frame_version, timeout=0.1)
            if frame is not None:
                cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                controller.toggle_target_lock()
            elif key in (ord("w"), ord("W")):
                controller.cycle_target_lock()
            elif key in (ord("t"), ord("T")):
                status = controller.get_status()["target_lock"]
                controller.set_target_lock_enabled(not status["enabled"])
            elif key == 27:
                break
    finally:
        cv2.destroyAllWindows()


def main() -> None:
    cv2.setNumThreads(1)
    controller = PipelineController()
    controller.start()
    atexit.register(controller.close)
    try:
        if config.VIDEO_OUTPUT == "web":
            create_app(controller).run(
                host=config.WEB_HOST,
                port=config.WEB_PORT,
                threaded=True,
                use_reloader=False,
            )
        elif config.VIDEO_OUTPUT == "vtx":
            show_vtx_output(controller)
        else:
            server = make_server(config.WEB_HOST, config.WEB_PORT, create_app(controller), threaded=True)
            web_thread = threading.Thread(target=server.serve_forever, name="drone-ai-web", daemon=True)
            web_thread.start()
            try:
                show_vtx_output(controller)
            finally:
                server.shutdown()
                server.server_close()
                web_thread.join(timeout=3.0)
    finally:
        controller.close()


if __name__ == "__main__":
    main()