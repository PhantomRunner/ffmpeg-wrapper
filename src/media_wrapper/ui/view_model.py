"""Presentation coordinator; invokes application services outside the event loop."""
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from media_wrapper.application.media_service import MediaService
from media_wrapper.application.remux_task import RemuxTask
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.ui.state import DesktopState
from media_wrapper.ui.workers import (
    DetectionWorker,
    InspectionWorker,
    RemuxPreparationWorker,
)

Worker = DetectionWorker | InspectionWorker | RemuxPreparationWorker


class DesktopViewModel(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = DesktopState()
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.remux_task: RemuxTask | None = None
        self._inspection_path: Path | None = None
        self._detecting = False

    def _start(self, worker: Worker, on_success: Callable[..., Any]) -> None:
        self.state.busy = True
        self.thread = QThread(self)
        self.worker = worker
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        worker.finished.connect(on_success)
        worker.failed.connect(self._failed)
        worker.finished.connect(self.thread.quit)
        worker.failed.connect(self.thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        self.thread.finished.connect(self._cleanup)
        self.changed.emit()
        self.thread.start()

    def detect(self, mode: str, directory: str | None) -> None:
        if self.state.busy:
            return
        self.state.binaries = None
        self.state.source = None
        self.state.status = 'Detecting FFmpeg…'
        self._detecting = True
        self._start(DetectionWorker(mode, directory), self._detected)

    @Slot(object)
    def _detected(self, binaries: Binaries) -> None:
        self.state.binaries = binaries
        self.state.status = f'Detected: {binaries.version}'
        self.changed.emit()

    def inspect(self, path: Path) -> None:
        if self.state.busy or self.state.binaries is None:
            return
        self.state.source = None
        self._inspection_path = path
        self.state.output = 'Inspecting…'
        self._start(InspectionWorker(MediaService(self.state.binaries), path), self._inspected)

    @Slot(str)
    def _inspected(self, text: str) -> None:
        self.state.source = self._inspection_path
        self.state.output = text
        self.changed.emit()

    def remux(self, destination: Path, container: Container) -> None:
        if self.state.busy or self.state.source is None or self.state.binaries is None:
            return
        self.state.output = 'Validating remux…'
        self._start(RemuxPreparationWorker(MediaService(self.state.binaries), self.state.source,
                                          destination, container), self.start_remux)

    @Slot(object)
    def start_remux(self, command: list[str]) -> None:
        self.state.output = 'Remux running…'
        self.state.busy = True
        self.remux_task = RemuxTask(self)
        self.remux_task.finished.connect(self._remux_complete)
        self.changed.emit()
        self.remux_task.start(command)

    @Slot(bool, str)
    def _remux_complete(self, success: bool, details: str) -> None:
        self.state.output = 'Remux complete.\n' + details if success else details
        if self.remux_task is not None:
            self.remux_task.deleteLater()
        self.remux_task = None
        self.state.busy = self.thread is not None
        self.changed.emit()

    @Slot(str)
    def _failed(self, error: str) -> None:
        self.state.output = error
        if self._detecting:
            self.state.status = error
        self.changed.emit()

    @Slot()
    def _cleanup(self) -> None:
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        self._detecting = False
        self.state.busy = self.remux_task is not None
        self.changed.emit()
