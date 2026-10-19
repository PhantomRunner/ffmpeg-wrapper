"""Sequential operation queue. Failures/cancellation do not stop later jobs."""
from dataclasses import replace

from PySide6.QtCore import QObject, QTimer, Signal

from media_wrapper.application.hardware_selection import cpu_retry_plan
from media_wrapper.application.operation_task import OperationTask
from media_wrapper.domain.operations import OperationPlan
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries


class TaskQueue(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.records: list[TaskRecord] = []
        self._binaries: dict[str, Binaries] = {}
        self.active: OperationTask | None = None
        self.running = False

    def add(self, plan: OperationPlan, binaries: Binaries) -> TaskRecord:
        # Every attempt receives a fresh temporary target at preparation time.
        plan = replace(plan, output=replace(plan.output, temporary_path=None))
        record = TaskRecord(plan)
        self.records.append(record)
        self._binaries[record.id] = binaries
        self.changed.emit()
        if self.running:
            QTimer.singleShot(0, self._next)
        return record

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.changed.emit()
        self._next()

    def _next(self) -> None:
        if self.active is not None or not self.running:
            return
        pending = next((r for r in self.records if r.status == TaskStatus.PENDING), None)
        if pending is None:
            self.running = False
            self.changed.emit()
            return
        task = OperationTask(pending, self._binaries[pending.id], self)
        self.active = task
        task.changed.connect(self.changed)
        task.finished.connect(self._finished)
        task.start()

    def _finished(self, _success: bool, _details: str) -> None:
        if self.active is not None:
            self.active.deleteLater()
        self.active = None
        self.changed.emit()
        QTimer.singleShot(0, self._next)

    def cancel(self, task_id: str) -> None:
        record = next(r for r in self.records if r.id == task_id)
        if record.status == TaskStatus.PENDING:
            record.transition(TaskStatus.CANCELLED)
            record.error = 'Cancelled before starting.'
        elif self.active is not None and self.active.record.id == task_id:
            self.active.cancel()
        self.changed.emit()

    def cancel_all(self) -> None:
        for record in self.records:
            self.cancel(record.id)

    def finished_history_ids(self) -> tuple[str, ...]:
        active_id = self.active.record.id if self.active is not None else None
        finished = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        return tuple(record.id for record in self.records
                     if record.status in finished and record.id != active_id)

    def clear_history(self, ids: tuple[str, ...] | None = None) -> tuple[str, ...]:
        # Optional IDs freeze the confirmation scope while other jobs finish.
        eligible = self.finished_history_ids()
        removed = tuple(task_id for task_id in eligible if ids is None or task_id in ids)
        if not removed:
            return ()
        self.records[:] = [record for record in self.records if record.id not in removed]
        for task_id in removed:
            self._binaries.pop(task_id, None)
        self.changed.emit()
        return removed

    def retry(self, task_id: str) -> TaskRecord:
        record = next(r for r in self.records if r.id == task_id)
        if record.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
            raise ValueError('Only failed or cancelled tasks can be retried')
        return self.add(record.plan, self._binaries[record.id])

    def retry_cpu(self, task_id: str) -> TaskRecord:
        record = next(r for r in self.records if r.id == task_id)
        if record.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
            raise ValueError('Only failed or cancelled GPU tasks can be retried on CPU')
        return self.add(cpu_retry_plan(record.plan), self._binaries[record.id])
