from __future__ import annotations

from typing import Any

from flask import Flask, Response, jsonify, render_template, request

from files.pipeline import PipelineController


def create_app(controller: PipelineController) -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/status")
    def status() -> Any:
        return jsonify(controller.get_status())

    @app.get("/video_feed")
    def video_feed() -> Response:
        def frames():
            version = -1
            while True:
                jpeg, version = controller.get_jpeg(version, timeout=5.0)
                if jpeg:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"

        return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.post("/api/control/<action>")
    def control(action: str) -> Any:
        payload = request.get_json(silent=True) or {}
        if action == "start":
            controller.set_paused(False)
        elif action == "pause":
            controller.set_paused(True)
        elif action == "restart":
            controller.restart()
        elif action == "ai":
            controller.set_ai_enabled(bool(payload.get("enabled", False)))
        elif action == "overlay":
            options = {
                key: bool(payload[key])
                for key in ("show_candidates", "show_confidence", "show_ids")
                if key in payload
            }
            controller.set_overlay(**options)
        else:
            return jsonify({"error": "Unknown action"}), 404
        return jsonify(controller.get_status())

    return app