"""Explicit installation check driven by the normal asynchronous desktop model."""
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    StreamSelection,
)
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.infrastructure.app_paths import AppPaths
from media_wrapper.infrastructure.json_documents import write_document


def verify_installation(source: Path, directory: Path) -> int:
    """Caller supplies a generated video/audio fixture and a new empty folder."""
    from media_wrapper.application.settings_service import SettingsService
    from media_wrapper.infrastructure.diagnostics import configure_logging
    from media_wrapper.infrastructure.settings_repository import SettingsRepository
    from media_wrapper.ui.main_window import MainWindow
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
    paths = AppPaths(directory / 'config', directory / 'data')
    diagnostics = configure_logging(paths)
    window = MainWindow(diagnostics.status, SettingsService(SettingsRepository(paths.settings_file)))
    app.aboutToQuit.connect(window.deleteLater)
    window.show()
    stage = 'detect'
    preview_frames = []
    playback = window.workspace.playback
    if playback.service:
        playback.video.videoSink().videoFrameChanged.connect(lambda frame: preview_frames.append(frame.isValid()))

    def finish(code: int, detail: str) -> None:
        write_document(directory / 'verification.json', {'success': code == 0, 'detail': detail,
                       'tasks': [r.status.value for r in window.model.queue.records],
                       'playback': {'decoded_video': any(preview_frames),
                                    'position_ms': playback.service.position if playback.service else 0}})
        window.close()
        app.exit(code)

    def advance() -> None:
        nonlocal stage
        model = window.model
        if model.state.busy:
            QTimer.singleShot(25, advance)
            return
        if stage == 'detect':
            if window.binaries is None:
                finish(2, model.state.status)
                return
            stage = 'inspect'
            model.inspect(source)
        elif stage == 'inspect':
            media = model.state.media
            if media is None or {s.kind for s in media.streams} != {'audio', 'video'}:
                finish(3, 'Inspection failed or fixture does not have video and audio')
                return
            model.queue.add(OperationPlan(MediaOperation.REMUX, media,
                            tuple(StreamSelection(s.index) for s in media.streams),
                            OutputTarget(directory / 'remux.mkv', Container.MATROSKA)), window.binaries)
            tracks = tuple((s.index, 'libx264' if s.kind == 'video' else 'aac') for s in media.streams)
            model.encode(ConversionRequest(directory / 'convert.mp4', Container.MP4, tracks,
                         operation=MediaOperation.CONVERT, mode='quality', preset='ultrafast', crf=28), 'enqueue')
            stage = 'enqueue-compress'
        elif stage == 'enqueue-compress':
            if len(model.queue.records) != 2:
                finish(4, 'Convert queue validation failed: ' + model.state.output)
                return
            tracks = tuple((s.index, 'libx264' if s.kind == 'video' else 'aac') for s in model.state.media.streams)
            model.encode(ConversionRequest(directory / 'compress.mp4', Container.MP4, tracks,
                         operation=MediaOperation.COMPRESS, mode='quality', preset='ultrafast', crf=28), 'enqueue')
            stage = 'start-queue'
        elif stage == 'start-queue':
            if len(model.queue.records) != 3:
                finish(4, 'Compress queue validation failed: ' + model.state.output)
                return
            stage = 'execute'
            model.start_queue()
        elif stage == 'execute':
            records = model.queue.records
            successful = len(records) == 3 and all(r.status == TaskStatus.COMPLETED for r in records)
            if not successful:
                finish(4, '\n'.join(r.error for r in records))
                return
            stage = 'preview-loading'
        elif stage == 'preview-loading':
            if not playback.service or playback.service.error:
                finish(5, playback.status.text())
                return
            if playback.service.ready:
                playback.service.toggle()
                stage = 'preview-playing'
        elif stage == 'preview-playing':
            if playback.service.error:
                finish(5, playback.service.error)
                return
            if playback.service.position >= 100 and any(preview_frames):
                finish(0, 'Verified inspect/remux/convert/compress and decoded preview playback')
                return
        QTimer.singleShot(25, advance)

    QTimer.singleShot(25, advance)
    try:
        return app.exec()
    finally:
        diagnostics.close()
