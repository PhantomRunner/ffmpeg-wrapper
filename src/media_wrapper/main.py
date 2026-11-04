"""Application entry point."""
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from media_wrapper.application.settings_service import SettingsService
from media_wrapper.infrastructure.app_paths import resolve_app_paths
from media_wrapper.infrastructure.diagnostics import configure_logging
from media_wrapper.infrastructure.settings_repository import SettingsRepository
from media_wrapper.ui.flat_main_window import MainWindow


def main() -> int:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    app = QApplication(sys.argv)
    app.setApplicationName('MediaWrapper')
    from media_wrapper.infrastructure.process_environment import (
        initialize_external_processes,
    )
    initialize_external_processes()
    app.setWindowIcon(QIcon(str(Path(__file__).parent / 'resources' / 'icon.svg')))
    paths = None
    try:
        paths = resolve_app_paths()
        diagnostics = configure_logging(paths)
    except OSError as error:
        diagnostics = configure_logging(None, str(error))
    try:
        window = MainWindow(diagnostic_status=diagnostics.status,
                            settings_service=SettingsService(SettingsRepository(paths.settings_file)) if paths else None,
                            layout_settings=QSettings('MediaWrapper', 'Workspace'))
        app.aboutToQuit.connect(window.deleteLater)
        window.show()
        if '--smoke-test' in sys.argv:
            def finish_smoke() -> None:
                if window.model.state.busy:
                    QTimer.singleShot(25, finish_smoke)
                    return
                app.exit(0 if window.binaries is not None else 2)
            QTimer.singleShot(25, finish_smoke)
        return app.exec()
    finally:
        diagnostics.close()


if __name__ == "__main__":
    raise SystemExit(main())
