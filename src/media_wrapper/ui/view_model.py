"""Presentation coordinator; invokes application services outside the event loop."""
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from media_wrapper.application.errors import ApplicationError, report_failure
from media_wrapper.application.file_service import validate_files
from media_wrapper.application.media_service import MediaService, validate_remux_paths
from media_wrapper.application.operation_task import OperationTask
from media_wrapper.application.remux_task import RemuxTask
from media_wrapper.application.task_queue import TaskQueue
from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operation_policy import validate_plan
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    PlanValidationError,
    StreamSelection,
)
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskRecord
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.ui.inspection_presenter import format_inspection
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
        self.remux_task: RemuxTask | OperationTask | None = None
        self._inspection_cancel = Event()
        self._inspection_paths: tuple[Path, ...] = ()
        self._detecting = False
        self.queue = TaskQueue(self)
        self.queue.changed.connect(self._queue_changed)

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
        self.state.inspections.clear()
        self.state.inspection_summary = ''
        self.state.stream_selections.clear()
        self.state.source = None
        self.state.media = None
        self.state.selected_streams = ()
        self.state.command = ()
        self.state.form_error = 'Detect FFmpeg and inspect a file first.'
        self.state.status = 'Binary selection changed. Click Detect FFmpeg.'
        self.changed.emit()

    def detect(self, mode: str, directory: str | None) -> None:
        if self.state.busy:
            return
        self.state.binaries = None
        self.state.inspections.clear()
        self.state.inspection_summary = ''
        self.state.stream_selections.clear()
        self.state.source = None
        self.state.media = None
        self.state.selected_streams = ()
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
        self.state.command = ()
        self._show_current_inspection()
        self.changed.emit()

    def _show_current_inspection(self) -> None:
        record = self.state.inspections.get(self.state.current_file) if self.state.current_file else None
        if record is not None and record.media is not None and record.status == InspectionStatus.COMPLETED:
            self._inspected(record.media)
        else:
            self.state.source = None
            self.state.media = None
            self.state.selected_streams = ()
            self.state.form_error = 'Inspect a file first.'
            self.state.output = (record.error or f'{record.path}: {record.status.value}') if record else ''

    def clear_files(self) -> None:
        if self.state.busy:
            return
        self.state.files = ()
        self.state.inspections.clear()
        self.state.inspection_summary = ''
        self.state.stream_selections.clear()
        self.state.inspection_summary = ''
        self.state.current_file = None
        self.state.source = None
        self.state.media = None
        self.state.selected_streams = ()
        self.state.command = ()
        self.state.form_error = 'Inspect a file first.'
        self.state.output = ''
        self.changed.emit()

    def inspect(self, path: Path) -> None:
        self.inspect_many((path,))

    def inspect_many(self, paths: tuple[Path, ...]) -> None:
        if self.state.busy or self.state.binaries is None or not paths:
            return
        self._inspection_paths = tuple(dict.fromkeys(paths))
        if self.state.current_file not in self._inspection_paths:
            self.state.current_file = self._inspection_paths[0]
        self._inspection_cancel = Event()
        self.state.inspection_active = True
        self.state.cancel_requested = False
        self.state.inspection_summary = f'Inspecting {len(self._inspection_paths)} file(s)…'
        for path in self._inspection_paths:
            self.state.inspections[path] = InspectionRecord(path, InspectionStatus.PENDING)
            self.state.stream_selections.pop(path, None)
        self.state.source = None
        self.state.media = None
        self.state.selected_streams = ()
        self.state.command = ()
        self.state.form_error = 'Inspection running…'
        self.state.output = 'Inspecting…'
        worker = InspectionWorker(MediaService(self.state.binaries), self._inspection_paths, self._inspection_cancel)
        worker.progress.connect(self._inspection_progress)
        self._start(worker, self._inspection_finished)

    def cancel_inspection(self) -> None:
        if self.state.inspection_active and not self.state.cancel_requested:
            self.state.cancel_requested = True
            self.state.inspection_summary = 'Cancelling inspection…'
            self._inspection_cancel.set()
            self.changed.emit()

    @Slot(object)
    def _inspection_progress(self, record: InspectionRecord) -> None:
        self.state.inspections[record.path] = record
        if record.path == self.state.current_file:
            self._show_current_inspection()
        self.changed.emit()

    @Slot(object)
    def _inspection_finished(self, results: tuple[InspectionRecord, ...]) -> None:
        for record in results:
            self.state.inspections[record.path] = record
        counts = {status: sum(record.status == status for record in results) for status in InspectionStatus}
        self.state.inspection_summary = (f'Inspection finished: {counts[InspectionStatus.COMPLETED]} completed, '
                                         f'{counts[InspectionStatus.FAILED]} failed, {counts[InspectionStatus.CANCELLED]} cancelled.')
        self._show_current_inspection()
        self.changed.emit()

    @Slot(object)
    def _inspected(self, info: MediaFile) -> None:
        self.state.source = info.path
        self.state.media = info
        self.state.selected_streams = self.state.stream_selections.setdefault(
            info.path, tuple(s.index for s in info.streams if s.index is not None))
        self.state.output = format_inspection(info)
        suffix = '.mkv' if self.state.container == Container.MATROSKA else '.mp4'
        if self.state.source is not None:
            self.state.destination = str((self.state.recent_destination or self.state.source.parent) /
                                         (self.state.source.stem + '_remux' + suffix))
        self._validate_form()
        self.changed.emit()

    def select_streams(self, indices: tuple[int, ...]) -> None:
        if self.state.busy or self.state.media is None:
            return
        available = {stream.index for stream in self.state.media.streams if stream.index is not None}
        if len(indices) != len(set(indices)) or not set(indices) <= available:
            return
        self.state.selected_streams = indices
        self.state.stream_selections[self.state.media.path] = indices
        self.state.command = ()
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
                if self.state.media is not None:
                    validate_plan(OperationPlan(MediaOperation.REMUX, self.state.media,
                                  tuple(StreamSelection(i) for i in self.state.selected_streams),
                                  OutputTarget(Path(self.state.destination).expanduser().absolute(), self.state.container)))
                self.state.form_error = ''
            except (ApplicationError, PlanValidationError) as error:
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
                                          Path(self.state.destination), self.state.container, self.state.selected_streams), self._preview_ready)

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
        if self.state.media is not None:
            plan = OperationPlan(MediaOperation.REMUX, self.state.media,
                                 tuple(StreamSelection(i) for i in self.state.selected_streams),
                                 OutputTarget(destination.expanduser().absolute(), container))
            self.state.busy = True
            task = OperationTask(TaskRecord(plan), self.state.binaries, self)
            self.remux_task = task
            task.finished.connect(self._remux_complete)
            task.changed.connect(self._task_changed)
            task.start()
            return

        self._start(RemuxPreparationWorker(MediaService(self.state.binaries), self.state.source,
                                          destination, container, self.state.selected_streams), self.start_remux)

    def enqueue_remux(self) -> None:
        if self.state.busy or self.state.media is None or self.state.binaries is None:
            return
        self._validate_form()
        if self.state.form_error:
            self.changed.emit()
            return
        plan = OperationPlan(MediaOperation.REMUX, self.state.media,
                             tuple(StreamSelection(i) for i in self.state.selected_streams),
                             OutputTarget(Path(self.state.destination).expanduser().absolute(), self.state.container))
        self.queue.add(plan, self.state.binaries)
        self.state.output = 'Added to queue. Start it on the Queue page.'
        self.changed.emit()

    def start_queue(self) -> None:
        if not self.state.busy:
            self.queue.start()

    @Slot()
    def _queue_changed(self) -> None:
        self.state.busy = self.queue.running or self.thread is not None or self.remux_task is not None
        self._validate_form()
        self.changed.emit()

    def cancel_remux(self) -> None:
        if isinstance(self.remux_task, OperationTask):
            self.remux_task.cancel()

    @Slot()
    def _task_changed(self) -> None:
        if isinstance(self.remux_task, OperationTask):
            record = self.remux_task.record
            self.state.command = record.command
            self.state.output = f'Remux: {record.status.value}'
            progress = record.progress
            percent = f'{progress.percent:.1f}%' if progress.percent is not None else 'percentage unknown'
            speed = f'{progress.speed:.2f}×' if progress.speed is not None else 'unknown'
            eta = f'{progress.eta:.1f}s' if progress.eta is not None else 'unknown'
            self.state.remux_progress = f'{record.status.value}: {percent}; estimated speed {speed}, ETA {eta}'
        self.changed.emit()

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
        if success and isinstance(self.remux_task, OperationTask) and self.remux_task.record.result is not None:
            self.state.output += '\nVerified output metadata:\n' + format_inspection(self.remux_task.record.result)
        if self.remux_task is not None:
            self.remux_task.deleteLater()
        self.remux_task = None
        self._validate_form()
        self.state.busy = self.thread is not None or self.queue.running
        self.changed.emit()

    @Slot(str)
    def _failed(self, error: str) -> None:
        if self.state.inspection_active:
            for path in self._inspection_paths:
                record = self.state.inspections[path]
                if record.status in (InspectionStatus.PENDING, InspectionStatus.RUNNING):
                    self.state.inspections[path] = InspectionRecord(path, InspectionStatus.FAILED, error=error)
            self.state.inspection_summary = 'Inspection failed. See the per-file errors.'
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
        self.state.inspection_active = False
        self.state.cancel_requested = False
        self.state.busy = self.remux_task is not None or self.queue.running
        self.changed.emit()
