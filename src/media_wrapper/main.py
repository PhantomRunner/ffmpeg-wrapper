"""Application entry point."""
import sys

from PySide6.QtWidgets import QApplication

from media_wrapper.infrastructure.app_paths import resolve_app_paths
from media_wrapper.infrastructure.diagnostics import configure_logging
from media_wrapper.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName('MediaWrapper')
    try:
        paths = resolve_app_paths()
        diagnostics = configure_logging(paths)
    except OSError as error:
        diagnostics = configure_logging(None, str(error))
    try:
        window = MainWindow(diagnostic_status=diagnostics.status)
        window.show()
        return app.exec()
    finally:
        diagnostics.close()


if __name__ == "__main__":
    raise SystemExit(main())
