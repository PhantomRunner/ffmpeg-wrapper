"""Explicit installation check of the normal flat UI and real FFmpeg pipeline."""
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from media_wrapper.domain.operations import MediaOperation
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.domain.workbench_preferences import WorkbenchPreferences
from media_wrapper.infrastructure.app_paths import AppPaths
from media_wrapper.infrastructure.json_documents import write_document


def verify_installation(source: Path, directory: Path) -> int:
    """Caller supplies a generated audio/video fixture and a new empty directory."""
    from media_wrapper.application.settings_service import SettingsService
    from media_wrapper.infrastructure.diagnostics import configure_logging
    from media_wrapper.infrastructure.history_repository import HistoryRepository
    from media_wrapper.infrastructure.installation_guard import InstallationGuard
    from media_wrapper.infrastructure.settings_repository import SettingsRepository
    from media_wrapper.ui.flat_main_window import MainWindow
    if not source.is_file() or not directory.is_dir() or any(directory.iterdir()):
        raise ValueError('Verification needs an existing fixture and an empty output directory')
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('MediaWrapperVerification')
    icon = QIcon(str(Path(__file__).parents[1] / 'resources/icon.svg'))
    if icon.pixmap(32, 32).isNull():
        raise RuntimeError('Packaged application icon could not be loaded')
    app.setWindowIcon(icon)
    from media_wrapper.infrastructure.process_environment import (
        initialize_external_processes,
    )
    initialize_external_processes()
    guard = InstallationGuard()
    paths = AppPaths(directory / 'config', directory / 'data')
    diagnostics = configure_logging(paths)
    history = HistoryRepository(paths.data_dir / 'history.json')
    window = MainWindow(diagnostics.status,
                        SettingsService(SettingsRepository(paths.settings_file), WorkbenchPreferences),
                        QSettings(str(paths.config_dir / 'layout.ini'), QSettings.Format.IniFormat),
                        history_repository=history)
    app.aboutToQuit.connect(window.deleteLater)
    window.show()
    stage, index, immutable = 'detect', 0, False
    operations = (MediaOperation.REMUX, MediaOperation.CONVERT, MediaOperation.COMPRESS)

    def finish(code, detail):
        controller = window.controller
        if controller.busy or controller.queue.running:
            controller.cancel_import()
            controller.validation_cancel.set()
            window.capability_cancel.set()
            controller.queue.cancel_all()
            QTimer.singleShot(25, lambda: finish(code, detail))
            return
        records = controller.queue.records
        window.close()
        write_document(directory / 'verification.json', {
            'success': code == 0, 'detail': detail, 'tasks': [r.status.value for r in records],
            'outputs_verified': len(records) == 3 and all(r.result is not None for r in records),
            'immutable_snapshots': immutable,
            'player_instantiated': any(child.metaObject().className() in ('QMediaPlayer', 'QVideoWidget')
                                       or child.objectName() == 'playbackPanel' for child in window.findChildren(QObject)),
            'history_persisted': len(history.read()) == 3 if code == 0 else False,
        })
        app.exit(code)

    def advance():
        nonlocal stage, index, immutable
        controller = window.controller
        if controller.busy or controller.queue.running:
            QTimer.singleShot(25, advance)
            return
        if stage == 'detect':
            if not window.binaries:
                finish(2, controller.status)
                return
            controller.import_sources((source,))
            stage = 'inspect'
        elif stage == 'inspect':
            items = tuple(controller.draft.items.values())
            if len(items) != 1 or not items[0].inspected or {s.kind for s in items[0].media.streams} != {'audio', 'video'}:
                finish(3, 'Inspection did not produce the expected audio/video source')
                return
            stage = 'configure'
        elif stage == 'configure':
            operation = operations[index]
            window.set_operation(operation)
            controller.patch('folder', str(directory))
            controller.patch('template', operation.value)
            controller.patch('container', Container.MATROSKA if operation == MediaOperation.REMUX else Container.MP4)
            if operation != MediaOperation.REMUX:
                controller.patch('mode', 'quality')
                controller.patch('preset', 'ultrafast')
                controller.patch('crf', 28)
            controller.prepare('enqueue')
            stage = 'enqueued'
        elif stage == 'enqueued':
            if len(controller.queue.records) != index + 1:
                errors = '\n'.join(i.validation.error for i in controller.preparation.items) if controller.preparation else controller.status
                finish(4, 'Queue preparation failed: ' + errors)
                return
            index += 1
            if index < len(operations):
                stage = 'configure'
            else:
                frozen = tuple(r.plan for r in controller.queue.records)
                controller.queue.start()
                controller.patch('audio_bitrate', 192000)
                immutable = frozen == tuple(r.plan for r in controller.queue.records)
                stage = 'execute'
        elif stage == 'execute':
            records = controller.queue.records
            successful = len(records) == 3 and all(r.status == TaskStatus.COMPLETED and r.result for r in records)
            finish(0 if successful and immutable else 4,
                   'Verified inspect/remux/convert/compress, immutable jobs and persisted history without a player'
                   if successful and immutable else '\n'.join(r.error for r in records))
            return
        QTimer.singleShot(25, advance)

    QTimer.singleShot(25, advance)
    QTimer.singleShot(90000, lambda: finish(6, 'Installation verification timed out'))
    try:
        return app.exec()
    finally:
        diagnostics.close()
        guard.close()
