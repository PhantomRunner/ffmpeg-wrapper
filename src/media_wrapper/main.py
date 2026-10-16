"""Application entry point."""
import sys

from PySide6.QtWidgets import QApplication

from media_wrapper.application.settings_service import SettingsService
from media_wrapper.infrastructure.app_paths import resolve_app_paths
from media_wrapper.infrastructure.diagnostics import configure_logging
from media_wrapper.infrastructure.settings_repository import SettingsRepository
from media_wrapper.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName('MediaWrapper')
    paths = None
    try:
        paths = resolve_app_paths()
        diagnostics = configure_logging(paths)
    except OSError as error:
        diagnostics = configure_logging(None, str(error))
    try:
        window = MainWindow(diagnostic_status=diagnostics.status,
                            settings_service=SettingsService(SettingsRepository(paths.settings_file)) if paths else None)
        window.show()
        return app.exec()
    finally:
        diagnostics.close()


if __name__ == "__main__":
    raise SystemExit(main())
