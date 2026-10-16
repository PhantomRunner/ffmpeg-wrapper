"""Sequential operation queue. Failures/cancellation do not stop later jobs."""
from dataclasses import replace

from PySide6.QtCore import QObject, QTimer, Signal

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

    def retry(self, task_id: str) -> TaskRecord:
        record = next(r for r in self.records if r.id == task_id)
        if record.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
            raise ValueError('Only failed or cancelled tasks can be retried')
        return self.add(record.plan, self._binaries[record.id])
