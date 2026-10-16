"""Asynchronous staged Remux lifecycle, reusable by the sequential queue."""
from collections.abc import Callable
from dataclasses import replace
from threading import Event
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from media_wrapper.application.errors import report_failure
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_service import prepare_command
from media_wrapper.domain.inspection import OperationCancelled
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import MediaOperation, OperationPlan
from media_wrapper.domain.progress import Progress
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.output_publication import publish_output
from media_wrapper.infrastructure.ffmpeg.process_runner import ProcessRunner


class _Work(QObject):
    done = Signal(bool, object)

    def __init__(self, action: Callable[[], Any]) -> None:
        super().__init__()
        self.action = action

    @Slot()
    def run(self) -> None:
        try:
            self.done.emit(True, self.action())
        except Exception as error:  # noqa: BLE001 - worker boundary
            self.done.emit(False, error)


class OperationTask(QObject):
    changed = Signal()
    finished = Signal(bool, str)

    def __init__(self, record: TaskRecord, binaries: Binaries, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.record, self.binaries = record, binaries
        self.cancel_event = Event()
        self.thread: QThread | None = None
        self.worker: _Work | None = None
        self.runner: ProcessRunner | None = None
        self.prepared: OperationPlan | None = None
        self._reply: tuple[bool, Any] | None = None
        self._callback: Callable[[Any], None] | None = None

    def start(self) -> None:
        self.record.transition(TaskStatus.PREPARING)
        self.changed.emit()
        self._work(self._prepare, self._run)

    def cancel(self) -> None:
        if self.record.status in (TaskStatus.PREPARING, TaskStatus.RUNNING):
            self.cancel_event.set()
            if self.runner is not None:
                self.runner.cancel()

    def _prepare(self) -> tuple[OperationPlan, list[str]]:
        if self.record.plan.operation != MediaOperation.REMUX:
            raise ValueError('This task runner currently supports Remux only')
        media = MediaService(self.binaries).inspect(self.record.plan.media.path, self.cancel_event)
        plan = replace(self.record.plan, media=media)
        prepared, _command = prepare_command(self.binaries.ffmpeg, plan)
        # Progress options belong to the infrastructure command builder.
        from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
        return prepared, CommandBuilder().build(self.binaries.ffmpeg, prepared, progress=True)

    def _work(self, action: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        self._callback = callback
        self._reply = None
        self.thread = QThread(self)
        self.worker = _Work(action)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self._received)
        self.worker.done.connect(self.thread.quit)
        self.worker.done.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._cleaned)
        self.thread.start()

    @Slot(bool, object)
    def _received(self, success: bool, value: Any) -> None:
        self._reply = success, value

    @Slot()
    def _cleaned(self) -> None:
        assert self.thread is not None and self._reply is not None
        self.thread.deleteLater()
        self.thread = None
        self.worker = None
        success, value = self._reply
        if not success:
            self._end(False, value)
        elif self._callback is not None:
            self._callback(value)

    def _run(self, result: tuple[OperationPlan, list[str]]) -> None:
        self.prepared, command = result
        self.record.partial_path = self.prepared.output.execution_path
        self.record.command = tuple(command)
        if self.cancel_event.is_set():
            self._end(False, OperationCancelled())
            return
        self.record.transition(TaskStatus.RUNNING)
        self.runner = ProcessRunner(self)
        self.runner.progress.connect(self._progress)
        self.runner.diagnostics.connect(self.record.append_log)
        self.runner.finished.connect(self._executed)
        self.changed.emit()
        self.runner.start(command, self.prepared.media.duration)

    @Slot(object)
    def _progress(self, progress: Progress) -> None:
        self.record.progress = progress
        self.changed.emit()

    @Slot(bool, str)
    def _executed(self, success: bool, details: str) -> None:
        self.record.append_log(details)
        if not success or self.cancel_event.is_set():
            self._end(False, RuntimeError(details))
        else:
            self._work(self._verify_publish, self._published)

    def _verify_publish(self) -> tuple[MediaFile, str]:
        assert self.prepared is not None
        output = self.prepared.output
        info = MediaService(self.binaries).inspect(output.execution_path, self.cancel_event)
        sources = {s.index: s for s in self.prepared.media.streams}
        expected = [(sources[s.index].kind, sources[s.index].codec) for s in self.prepared.streams]
        if [(s.kind, s.codec) for s in info.streams] != expected or not info.size_bytes:
            raise ValueError('Output verification failed: selected stream codecs/count or file size differ')
        if self.cancel_event.is_set():
            raise OperationCancelled()
        # Publication is the commit point: once linked, report completion even if a
        # cancellation arrives immediately afterwards. Never erase a published file.
        warning = publish_output(output.execution_path, output.path)
        return replace(info, path=output.path), warning

    def _published(self, result: tuple[MediaFile, str]) -> None:
        self.record.result, warning = result
        self.record.append_log(warning)
        self.record.transition(TaskStatus.COMPLETED)
        self.changed.emit()
        self.finished.emit(True, f'Output: {self.record.result.path}\n{warning}')

    def _end(self, success: bool, error: Exception) -> None:
        if self.cancel_event.is_set() or isinstance(error, OperationCancelled):
            self.record.transition(TaskStatus.CANCELLED)
            message = 'Remux cancelled.'
        else:
            self.record.transition(TaskStatus.FAILED)
            message = report_failure('Remux', error)
        if self.record.partial_path is not None:
            message += f'\nPartial output may remain: {self.record.partial_path}'
        self.record.error = message
        self.record.append_log(message)
        self.changed.emit()
        self.finished.emit(False, message)
