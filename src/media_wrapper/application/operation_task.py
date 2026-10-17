"""Asynchronous staged Remux lifecycle, reusable by the sequential queue."""
import json
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot

from media_wrapper.application.errors import report_failure
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_service import prepare_operation
from media_wrapper.domain.inspection import OperationCancelled
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operation_policy import ENCODERS
from media_wrapper.domain.operations import OperationPlan
from media_wrapper.domain.progress import Progress
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders
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
        self._remaining_commands: list[list[str]] = []
        self._pass_directory: Path | None = None
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
        media = MediaService(self.binaries).inspect(self.record.plan.media.path, self.cancel_event)
        plan = replace(self.record.plan, media=media)
        available = list_encoders(self.binaries.ffmpeg, self.cancel_event) if any(s.profile.encoder != 'copy' for s in plan.streams) else frozenset()
        prepared = prepare_operation(plan, available_encoders=available)
        # Progress options belong to the infrastructure command builder.
        from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
        prefix = prepared.output.execution_path.with_suffix('.passlog')
        if prepared.two_pass:
            self._pass_directory = Path(tempfile.mkdtemp(prefix='media-wrapper-pass-'))
            prefix = self._pass_directory / 'pass'
        commands = CommandBuilder().build_passes(self.binaries.ffmpeg, prepared, available, prefix)
        self._remaining_commands = commands[1:]
        return prepared, commands[0]

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
            self._end(value)
        elif self._callback is not None:
            self._callback(value)

    def _run(self, result: tuple[OperationPlan, list[str]]) -> None:
        self.prepared, command = result
        self.record.partial_path = self.prepared.output.execution_path
        self.record.command = tuple(command)
        if self.cancel_event.is_set():
            self._end(OperationCancelled())
            return
        self.record.transition(TaskStatus.RUNNING)
        self._start_command(command)

    def _start_command(self, command: list[str]) -> None:
        self.record.command = tuple(command)
        self.record.append_log("\nArguments: " + json.dumps(command) + "\n")
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
            self._end(RuntimeError(details))
        elif self._remaining_commands:
            self.runner.deleteLater()
            self._start_command(self._remaining_commands.pop(0))
        else:
            self._work(self._verify_publish, self._published)

    def _verify_publish(self) -> tuple[MediaFile, str]:
        assert self.prepared is not None
        output = self.prepared.output
        info = MediaService(self.binaries).inspect(output.execution_path, self.cancel_event)
        sources = {s.index: s for s in self.prepared.media.streams}
        expected = [(sources[s.index].kind, sources[s.index].codec if s.profile.encoder == 'copy' else ENCODERS[s.profile.encoder][1]) for s in self.prepared.streams]
        if [(s.kind, s.codec) for s in info.streams] != expected or not info.size_bytes:
            raise ValueError('Output verification failed: selected stream codecs/count or file size differ')
        for output_stream, selected in zip(info.streams, self.prepared.streams, strict=True):
            profile = selected.profile
            if profile.width is not None and (output_stream.width, output_stream.height) != (profile.width, profile.height):
                raise ValueError('Output resolution verification failed')
            if profile.fps is not None and output_stream.frame_rate != profile.fps:
                raise ValueError('Output frame rate verification failed')
        if self.cancel_event.is_set():
            raise OperationCancelled()
        # Publication is the commit point: once linked, report completion even if a
        # cancellation arrives immediately afterwards. Never erase a published file.
        if self._pass_directory is not None:
            shutil.rmtree(self._pass_directory)
            self._pass_directory = None
        warning = publish_output(output.execution_path, output.path)
        return replace(info, path=output.path), warning

    def _published(self, result: tuple[MediaFile, str]) -> None:
        self.record.result, warning = result
        self.record.append_log(warning)
        self.record.transition(TaskStatus.COMPLETED)
        self.changed.emit()
        self.finished.emit(True, f'Output: {self.record.result.path}\n{warning}')

    def _end(self, error: Exception) -> None:
        # Keep pass logs on failure for diagnosis, just like partial media.
        if self._pass_directory is not None:
            self.record.append_log(f'\nPass logs retained: {self._pass_directory}\n')
            self._pass_directory = None
        if self.cancel_event.is_set() or isinstance(error, OperationCancelled):
            self.record.transition(TaskStatus.CANCELLED)
            message = f'{self.record.plan.operation.value.title()} cancelled.'
        else:
            self.record.transition(TaskStatus.FAILED)
            message = report_failure(self.record.plan.operation.value.title(), error)
        if self.record.partial_path is not None:
            message += f'\nPartial output may remain: {self.record.partial_path}'
        self.record.error = message
        self.record.append_log(message)
        self.changed.emit()
        self.finished.emit(False, message)
