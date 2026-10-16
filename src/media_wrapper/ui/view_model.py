"""Presentation coordinator; invokes application services outside the event loop."""
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from media_wrapper.application.errors import ApplicationError, report_failure
from media_wrapper.application.file_service import validate_files
from media_wrapper.application.media_service import MediaService, validate_remux_paths
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

    def binary_selection_changed(self) -> None:
        if self.state.busy:
            return
        self.state.binaries = None
        self.state.source = None
        self.state.command = ()
        self.state.form_error = 'Detect FFmpeg and inspect a file first.'
        self.state.status = 'Binary selection changed. Click Detect FFmpeg.'
        self.changed.emit()

    def detect(self, mode: str, directory: str | None) -> None:
        if self.state.busy:
            return
        self.state.binaries = None
        self.state.source = None
        self.state.command = ()
        self.state.form_error = 'Inspect a file first.'
        self.state.status = 'Detecting FFmpeg…'
        self._detecting = True
        self._start(DetectionWorker(mode, directory), self._detected)

    @Slot(object)
    def _detected(self, binaries: Binaries) -> None:
        self.state.binaries = binaries
        self.state.status = f'Detected: {binaries.version}'
        self.changed.emit()

    def add_files(self, paths: list[Path]) -> None:
        if self.state.busy:
            return
        try:
            additions = validate_files(paths)
        except ApplicationError as error:
            self.state.output = report_failure('File selection', error)
            self.changed.emit()
            return
        self.state.files = tuple(dict.fromkeys((*self.state.files, *additions)))
        if self.state.current_file is None and self.state.files:
            self.select_file(self.state.files[0])
        self.changed.emit()

    def select_file(self, path: Path | None) -> None:
        if self.state.busy or path == self.state.current_file:
            return
        self.state.current_file = path
        self.state.source = None
        self.state.command = ()
        self.state.form_error = 'Inspect a file first.'
        self.state.output = ''
        self.changed.emit()

    def clear_files(self) -> None:
        if self.state.busy:
            return
        self.state.files = ()
        self.state.current_file = None
        self.state.source = None
        self.state.command = ()
        self.state.form_error = 'Inspect a file first.'
        self.state.output = ''
        self.changed.emit()

    def inspect(self, path: Path) -> None:
        if self.state.busy or self.state.binaries is None:
            return
        self.state.source = None
        self.state.command = ()
        self.state.form_error = 'Inspect a file first.'
        self._inspection_path = path
        self.state.output = 'Inspecting…'
        self._start(InspectionWorker(MediaService(self.state.binaries), path), self._inspected)

    @Slot(str)
    def _inspected(self, text: str) -> None:
        self.state.source = self._inspection_path
        self.state.output = text
        suffix = '.mkv' if self.state.container == Container.MATROSKA else '.mp4'
        if self.state.source is not None:
            self.state.destination = str((self.state.recent_destination or self.state.source.parent) /
                                         (self.state.source.stem + '_remux' + suffix))
        self._validate_form()
        self.changed.emit()

    def set_output(self, destination: str, container: Container) -> None:
        if self.state.busy:
            return
        self.state.destination = destination
        self.state.container = container
        self.state.command = ()
        self._validate_form()
        self.changed.emit()

    def _validate_form(self) -> None:
        if self.state.source is None:
            self.state.form_error = 'Inspect a file first.'
        elif not self.state.destination.strip():
            self.state.form_error = 'Choose a new output filename.'
        else:
            try:
                validate_remux_paths(self.state.source, Path(self.state.destination), self.state.container)
                self.state.form_error = ''
            except ApplicationError as error:
                self.state.form_error = str(error)

    def preview(self) -> None:
        if self.state.busy or self.state.binaries is None or self.state.source is None:
            return
        self._validate_form()
        if self.state.form_error:
            self.changed.emit()
            return
        self.state.command = ()
        self._start(RemuxPreparationWorker(MediaService(self.state.binaries), self.state.source,
                                          Path(self.state.destination), self.state.container), self._preview_ready)

    @Slot(object)
    def _preview_ready(self, command: list[str]) -> None:
        self.state.command = tuple(command)
        self.state.output = 'Command validated. Review the argument array before running.'
        self.changed.emit()

    def remux(self, destination: Path, container: Container) -> None:
        if self.state.busy or self.state.source is None or self.state.binaries is None:
            return
        self.state.recent_destination = destination.parent
        self.state.command = ()
        self.state.output = 'Validating remux…'
        self._start(RemuxPreparationWorker(MediaService(self.state.binaries), self.state.source,
                                          destination, container), self.start_remux)

    @Slot(object)
    def start_remux(self, command: list[str]) -> None:
        self.state.command = tuple(command)
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
        self._validate_form()
        self.state.busy = self.thread is not None
        self.changed.emit()

    @Slot(str)
    def _failed(self, error: str) -> None:
        self.state.output = error
        self.state.command = ()
        self._validate_form()
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
