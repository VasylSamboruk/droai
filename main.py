import atexit

from files.pipeline import PipelineController
from files.web import create_app
import config


def main() -> None:
    controller = PipelineController()
    controller.start()
    atexit.register(controller.close)
    app = create_app(controller)
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()