"""Asynchronous staged Remux lifecycle, reusable by the sequential queue."""
import json
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from media_wrapper.application.errors import report_failure
from media_wrapper.application.hardware_selection import cpu_retry_plan
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_service import prepare_operation
from media_wrapper.application.operation_validation import (
    path_identity,
    source_identity,
)
from media_wrapper.application.output_verification import verify_output
from media_wrapper.domain.capabilities import GPU_ENCODERS, EncoderStatus
from media_wrapper.domain.inspection import OperationCancelled
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import OperationPlan
from media_wrapper.domain.progress import Progress
from media_wrapper.domain.target_size import tighten_target_size
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders
from media_wrapper.infrastructure.ffmpeg.gpu_probe import test_gpu_encoder
from media_wrapper.infrastructure.ffmpeg.muxers import require_muxer
from media_wrapper.infrastructure.ffmpeg.output_publication import publish_output
from media_wrapper.infrastructure.ffmpeg.probe_service import run_cancellable_probe
from media_wrapper.infrastructure.ffmpeg.process_runner import ProcessRunner


@dataclass(frozen=True)
class _Oversized:
    actual_bytes: int


_MAX_CORRECTIONS = 2


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
        self._owner_thread = QThread.currentThread()
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
        self._available_encoders: frozenset[str] = frozenset()
        self._source_identity: tuple[int, int, int, int] | None = None
        self._destination_identity: tuple[int, int] | None = None
        self._corrections = 0

    def start(self) -> None:
        self.record.transition(TaskStatus.PREPARING)
        self.record.stage = 'Checking source and destination'
        self.changed.emit()
        self._work(self._prepare, self._run)

    def cancel(self) -> None:
        if self.record.status in (TaskStatus.PREPARING, TaskStatus.RUNNING):
            self.record.cancel_requested = True
            self.cancel_event.set()
            self.changed.emit()
            if self.runner is not None:
                self.runner.cancel()

    def _prepare(self) -> tuple[OperationPlan, list[str]]:
        self._source_identity = source_identity(self.record.plan.media.path)
        fingerprint = self._source_identity[2:]
        if self.record.source_fingerprint is not None and self.record.source_fingerprint != fingerprint:
            raise ValueError('Source changed since this job was prepared. Inspect it and create a new draft.')
        self.record.source_fingerprint = fingerprint
        media = MediaService(self.binaries).inspect(self.record.plan.media.path, self.cancel_event)
        plan = replace(self.record.plan, media=media)
        require_muxer(self.binaries.ffmpeg, plan.output.container, self.cancel_event)
        available = list_encoders(self.binaries.ffmpeg, self.cancel_event) if any(s.profile.encoder != 'copy' for s in plan.streams) else frozenset()
        self._available_encoders = available
        for encoder in {s.profile.encoder for s in plan.streams} & set(GPU_ENCODERS):
            failure = self._gpu_failure(encoder, plan)
            if failure:
                if not plan.cpu_fallback:
                    raise RuntimeError(failure)
                plan = replace(cpu_retry_plan(plan), hardware_note=f'{failure} Authorized CPU fallback selected.')
                break
        prepared = prepare_operation(plan, available_encoders=available)
        self._destination_identity = path_identity(prepared.output.path.parent)
        self._check_paths(prepared)
        return prepared, self._first_command(prepared)

    def _gpu_failure(self, encoder: str, plan: OperationPlan) -> str | None:
        if encoder not in self._available_encoders:
            return f'{encoder} is unavailable in the selected FFmpeg build.'
        tested = test_gpu_encoder(self.binaries.ffmpeg, encoder, self.cancel_event, plan.hardware_device)
        if tested.status != EncoderStatus.WORKING:
            return f'{encoder} runtime initialization failed: {tested.detail}. Select Retry on CPU in Queue or fix the device/driver.'
        return None

    def _first_command(self, plan: OperationPlan) -> list[str]:
        prefix = plan.output.execution_path.with_suffix('.passlog')
        if plan.two_pass:
            if self._pass_directory is None:
                self._pass_directory = Path(tempfile.mkdtemp(prefix='media-wrapper-pass-'))
            prefix = self._pass_directory / f'pass-{self._corrections}'
        commands = CommandBuilder().build_passes(self.binaries.ffmpeg, plan, self._available_encoders, prefix)
        self._remaining_commands = commands[1:]
        return commands[0]

    def _check_paths(self, plan: OperationPlan) -> None:
        if source_identity(plan.media.path) != self._source_identity:
            raise ValueError('Source changed during processing. Inspect it and create a new draft.')
        if path_identity(plan.output.path.parent) != self._destination_identity:
            raise ValueError('Destination directory changed during processing. Reconnect the intended drive.')

    def _work(self, action: Callable[[], Any], callback: Callable[[Any], None]) -> None:
        self._callback = callback
        self._reply = None
        self.thread = QThread(self)
        self.worker = _Work(action)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self._return_worker, Qt.ConnectionType.DirectConnection)
        self.worker.done.connect(self._received, Qt.ConnectionType.QueuedConnection)
        self.worker.done.connect(self.thread.quit, Qt.ConnectionType.QueuedConnection)
        self.thread.finished.connect(self._cleaned, Qt.ConnectionType.QueuedConnection)
        self.thread.start()

    @Slot(bool, object)
    def _received(self, success: bool, value: Any) -> None:
        self._reply = success, value

    @Slot()
    def _return_worker(self) -> None:
        self.worker.moveToThread(self._owner_thread)

    @Slot()
    def _cleaned(self) -> None:
        assert self.thread is not None and self._reply is not None
        self.worker.deleteLater()
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
        self.record.append_log(self.prepared.hardware_note + "\n")
        self.record.partial_path = self.prepared.output.execution_path
        self.record.command = tuple(command)
        self.record.pass_count = len(self._remaining_commands) + 1
        if self.cancel_event.is_set():
            self._end(OperationCancelled())
            return
        self.record.transition(TaskStatus.RUNNING)
        self._start_command(command)

    def _start_command(self, command: list[str]) -> None:
        self.record.command = tuple(command)
        self.record.commands += (tuple(command),)
        self.record.pass_index += 1
        self.record.stage = f'Encoding pass {self.record.pass_index} of {self.record.pass_count}'
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
            self._end(RuntimeError(details), detail=self.runner.error_output.strip()
                      or 'FFmpeg did not provide an error message.')
        elif self._remaining_commands:
            self.runner.deleteLater()
            self._start_command(self._remaining_commands.pop(0))
        else:
            self.record.stage = 'Verifying output'
            self.changed.emit()
            self._work(self._verify_publish, self._published)

    def _verify_publish(self) -> tuple[MediaFile, str] | _Oversized:
        assert self.prepared is not None
        plan, output = self.prepared, self.prepared.output
        self._check_paths(plan)
        temporary = output.execution_path
        if temporary.is_symlink():
            raise ValueError('Temporary output was replaced by a symbolic link')
        staged_file = source_identity(temporary)
        actual_bytes = staged_file[2]
        info = MediaService(self.binaries).inspect(temporary, self.cancel_event)
        if info.size_bytes != actual_bytes:
            raise ValueError('FFprobe and filesystem disagree on the staged output size')
        if plan.target_size_bytes is not None and actual_bytes > plan.target_size_bytes:
            return _Oversized(actual_bytes)
        verify_output(plan, info)
        if plan.deep_verify and any(s.kind in {'video', 'audio'} and not s.is_artwork for s in info.streams):
            self._verify_decode(info)
        self._check_paths(plan)
        if temporary.is_symlink() or source_identity(temporary) != staged_file:
            raise ValueError('Temporary output changed during verification')
        if self.cancel_event.is_set():
            raise OperationCancelled()
        before_publication = getattr(self.record, 'before_publication', None)
        if before_publication is not None:
            before_publication(temporary, output.path, info)
        warning = publish_output(temporary, output.path)
        if self._pass_directory is not None:
            shutil.rmtree(self._pass_directory, ignore_errors=True)
            self._pass_directory = None
        return replace(info, path=output.path), warning

    def _verify_decode(self, info: MediaFile) -> None:
        args = [str(self.binaries.ffmpeg), '-hide_banner', '-nostdin', '-v', 'error', '-xerror',
                '-i', str(info.path), '-map', '0:V?', '-map', '0:a?', '-f', 'null', '-']
        timeout = min(86_400, max(90, (info.duration or 0) * 4))
        result = run_cancellable_probe(args, self.cancel_event, timeout=timeout)
        if result.returncode:
            raise ValueError(f'Full decode failed: {result.stderr.strip()}')

    def _retry_size(self, actual_bytes: int) -> None:
        assert self.prepared is not None
        plan = self.prepared
        corrected = tighten_target_size(plan, actual_bytes) if self._corrections < _MAX_CORRECTIONS else None
        if corrected is None:
            self._end(ValueError(f'Strict size limit failed: {actual_bytes:,} bytes exceeds {plan.target_size_bytes:,} bytes'))
            return
        if self.cancel_event.is_set():
            self._end(OperationCancelled())
            return
        self._corrections += 1
        try:
            self._check_paths(plan)
            plan.output.execution_path.unlink()
            self.prepared = corrected
            command = self._first_command(corrected)
        except (OSError, ValueError) as error:
            self._end(error)
            return
        self.record.append_log(f'Staged output was {actual_bytes:,} bytes. Size correction {self._corrections} of {_MAX_CORRECTIONS}.\n')
        self.record.pass_index = 0
        self.record.progress = None
        self.runner.deleteLater()
        self._start_command(command)

    def _published(self, result: tuple[MediaFile, str] | _Oversized) -> None:
        if isinstance(result, _Oversized):
            self._retry_size(result.actual_bytes)
            return
        self.record.result, warning = result
        self.record.append_log(warning)
        self.record.stage = 'Verified and published'
        self.record.transition(TaskStatus.COMPLETED)
        self.changed.emit()
        self.finished.emit(True, f'Output: {self.record.result.path}\n{warning}')

    def _end(self, error: Exception, *, detail: str | None = None) -> None:
        self.record.failure_detail = str(error) if detail is None else detail
        self.record.append_log(str(error) + "\n")
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
        self.record.stage = self.record.status.value
        self.record.append_log(message)
        self.changed.emit()
        self.finished.emit(False, message)
