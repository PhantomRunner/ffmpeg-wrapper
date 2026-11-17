"""Sequential queue with immutable plans and durable state at execution boundaries."""
import sqlite3
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from media_wrapper.application.hardware_selection import cpu_retry_plan
from media_wrapper.application.operation_task import OperationTask
from media_wrapper.domain.operations import OperationPlan
from media_wrapper.domain.tasks import RETRYABLE, TERMINAL, TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.queue_store import QueueStore


class TaskQueue(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.records: list[TaskRecord] = []
        self._binaries: dict[str, Binaries] = {}
        self._recovery_binaries: Binaries | None = None
        self.active: OperationTask | None = None
        self.running = False
        self.stop_requested = False
        self.stop_on_error = False
        self.persistence_error = ''
        self.runtime_notice = ''
        self.batch_ids = set()
        self._store: QueueStore | None = None
        self._storage_requested = False
        self._active_state = None

    @property
    def persistent(self) -> bool:
        return self._store is not None

    def enable_persistence(self, path: Path, log_dir: Path) -> None:
        if self._storage_requested or self.records or self.active is not None:
            raise RuntimeError('Queue storage must be configured before adding jobs.')
        self._storage_requested = True
        store = None
        try:
            store = QueueStore(path, log_dir)
            restored = store.restore()
            self.stop_on_error = store.option('stop_on_error')
        except (OSError, sqlite3.Error, ValueError) as error:
            if store is not None:
                store.close()
            self._storage_problem(error)
        else:
            self._store = store
            self.records.extend(restored)
        self.changed.emit()

    def close_store(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None

    def bind_recovered_binaries(self, binaries: Binaries | None) -> None:
        """Restarted jobs use the currently validated FFmpeg installation."""
        self._recovery_binaries = binaries

    def import_legacy_history(self, records: tuple[TaskRecord, ...]) -> None:
        if self._store is None:
            return
        try:
            self.records.extend(self._store.migrate(records))
        except (OSError, sqlite3.Error, ValueError) as error:
            self._storage_problem(error)
        self.changed.emit()

    def _storage_problem(self, error: Exception) -> None:
        self.persistence_error = f'Queue storage is unavailable. Close other instances or repair storage, then restart. {error}'
        if self.active is None:
            self.running = False
        else:
            self.stop_requested = True

    def _write(self, operation, *args, **kwargs) -> bool:
        if self._store is None:
            return not self._storage_requested
        try:
            operation(*args, **kwargs)
        except (OSError, sqlite3.Error, ValueError) as error:
            self._storage_problem(error)
            return False
        return True

    def add(self, plan: OperationPlan, binaries: Binaries) -> TaskRecord:
        records = self.add_many((plan,), binaries)
        if not records:
            raise OSError(self.persistence_error or 'The queue is closed.')
        return records[0]

    def add_many(self, plans: tuple[OperationPlan, ...], binaries: Binaries, *, fingerprints=None) -> tuple[TaskRecord, ...]:
        """Insert an immutable batch in one transaction, then notify the views."""
        if not plans or self.persistence_error or (self._storage_requested and self._store is None):
            return ()
        records = tuple(TaskRecord(replace(plan, output=replace(plan.output, temporary_path=None))) for plan in plans)
        for record in records:
            record.binary_version = binaries.version
            record.source_fingerprint = (fingerprints or {}).get(record.plan.media.path)
            if self._store is not None:
                record.log_path = self._store.log_path(record.id)
                if record.source_fingerprint is None:
                    try:
                        info = record.plan.media.path.stat()
                    except OSError:
                        # Reappearing input must be explicitly inspected again.
                        record.source_fingerprint = (0, -1)
                    else:
                        record.source_fingerprint = info.st_size, info.st_mtime_ns
        if self._store and not self._write(self._store.add, records):
            self.changed.emit()
            return ()
        self.records.extend(records)
        self._binaries.update((record.id, binaries) for record in records)
        self.changed.emit()
        if self.running:
            self.batch_ids.update(record.id for record in records)
            QTimer.singleShot(0, self._next)
        return records

    def start(self) -> None:
        if self.running or self.persistence_error or (self._storage_requested and self._store is None):
            return
        self.runtime_notice = ''
        self.stop_requested = False
        self.batch_ids = {r.id for r in self.records if r.status == TaskStatus.PENDING}
        self.running = True
        self.changed.emit()
        self._next()

    def stop_after_current(self) -> None:
        if self.active is None:
            self.running = False
        else:
            self.stop_requested = True
        self.changed.emit()

    def set_stop_on_error(self, stop: bool) -> None:
        if self._store and not self._write(self._store.set_option, 'stop_on_error', stop):
            self.changed.emit()
            return
        self.stop_on_error = stop
        self.changed.emit()

    def _next(self) -> None:
        if self.active is not None or not self.running:
            return
        pending = next((r for r in self.records if r.status == TaskStatus.PENDING), None)
        if pending is None:
            self.running = False
            self.changed.emit()
            return
        binaries = self._binaries.get(pending.id) or self._recovery_binaries
        if binaries is None:
            self.running = False
            self.runtime_notice = 'Select a working FFmpeg installation in Settings before starting recovered jobs.'
            self.changed.emit()
            return
        pending.binary_version = binaries.version
        if self._store is not None:
            launch = replace(pending)
            launch.transition(TaskStatus.PREPARING)
            if not self._write(self._store.update, launch):
                self.changed.emit()
                return
            pending.before_publication = lambda staged, final, result: self._store.before_publish(
                pending, staged, final, result,
            )
        task = OperationTask(pending, binaries, self)
        self._active_state = None
        self.active = task
        task.changed.connect(self._task_changed)
        task.finished.connect(self._finished)
        task.start()

    def _task_changed(self) -> None:
        if self.active is not None and self._store is not None:
            record = self.active.record
            state = (record.status, record.partial_path, record.pass_index, record.stage)
            if state != self._active_state and record.status not in TERMINAL:
                self._active_state = state
                self._write(self._store.update, record)
        self.changed.emit()

    def _finished(self, _success: bool, _details: str) -> None:
        if self.active is not None:
            record = self.active.record
            if self._store is not None:
                self._write(self._store.update, record, terminal=True)
                record.before_publication = None
            if self.stop_requested or (self.stop_on_error and record.status == TaskStatus.FAILED):
                self.running = False
                self.stop_requested = False
            self.active.deleteLater()
        self.active = None
        self.changed.emit()
        QTimer.singleShot(0, self._next)

    def cancel(self, task_id: str) -> None:
        record = next(r for r in self.records if r.id == task_id)
        if record.status == TaskStatus.PENDING:
            cancelled = replace(record)
            cancelled.transition(TaskStatus.CANCELLED)
            cancelled.error = 'Cancelled before starting.'
            if self._store is None or self._write(self._store.update, cancelled, terminal=True):
                # Keep the record identity for views and observers holding it.
                record.transition(TaskStatus.CANCELLED)
                record.finished_at = cancelled.finished_at
                record.error = cancelled.error
        elif self.active is not None and self.active.record.id == task_id:
            self.active.cancel()
        self.changed.emit()

    def cancel_all(self) -> None:
        for record in self.records:
            self.cancel(record.id)

    def move_pending(self, task_id: str, direction: int) -> bool:
        pending = [r for r in self.records if r.status == TaskStatus.PENDING]
        index = next((i for i, record in enumerate(pending) if record.id == task_id), None)
        if index is None or direction not in (-1, 1) or not 0 <= index + direction < len(pending):
            return False
        other = pending[index + direction]
        if self._store and not self._write(self._store.move, task_id, other.id):
            self.changed.emit()
            return False
        first = self.records.index(pending[index])
        second = self.records.index(other)
        self.records[first], self.records[second] = self.records[second], self.records[first]
        self.changed.emit()
        return True

    def remove_pending(self, ids: tuple[str, ...]) -> tuple[str, ...]:
        return self._remove(tuple(r.id for r in self.records if r.status == TaskStatus.PENDING and r.id in ids))

    def finished_history_ids(self) -> tuple[str, ...]:
        active_id = self.active.record.id if self.active is not None else None
        return tuple(r.id for r in self.records if r.status in TERMINAL and r.id != active_id)

    def clear_history(self, ids: tuple[str, ...] | None = None) -> tuple[str, ...]:
        eligible = self.finished_history_ids()
        return self._remove(tuple(task_id for task_id in eligible if ids is None or task_id in ids))

    def _remove(self, removed: tuple[str, ...]) -> tuple[str, ...]:
        if not removed:
            return ()
        if self._store and not self._write(self._store.delete, removed):
            self.changed.emit()
            return ()
        self.records[:] = [r for r in self.records if r.id not in removed]
        self.batch_ids.difference_update(removed)
        for task_id in removed:
            self._binaries.pop(task_id, None)
        self.changed.emit()
        return removed

    def retry(self, task_id: str) -> TaskRecord:
        record, binaries = self._retry_context(task_id)
        return self._retry_attempt(record, record.plan, binaries)

    def retry_cpu(self, task_id: str) -> TaskRecord:
        record, binaries = self._retry_context(task_id)
        return self._retry_attempt(record, cpu_retry_plan(record.plan), binaries)

    def _retry_attempt(self, record: TaskRecord, plan: OperationPlan, binaries: Binaries) -> TaskRecord:
        items = self.add_many((plan,), binaries, fingerprints={plan.media.path: record.source_fingerprint})
        if not items:
            raise OSError(self.persistence_error or 'The queue is closed.')
        return items[0]

    def _retry_context(self, task_id: str) -> tuple[TaskRecord, Binaries]:
        record = next(r for r in self.records if r.id == task_id)
        if record.status not in RETRYABLE:
            raise ValueError('Only failed, cancelled or interrupted tasks can be retried')
        binaries = self._binaries.get(record.id) or self._recovery_binaries
        if binaries is None:
            raise ValueError('Select a working FFmpeg installation before retrying this task.')
        if self.persistence_error:
            raise OSError(self.persistence_error)
        return record, binaries
