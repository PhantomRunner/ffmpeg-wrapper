"""Task lifecycle and legal transitions, independent of Qt."""
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from time import monotonic
from uuid import uuid4

from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import OperationPlan
from media_wrapper.domain.progress import Progress


class TaskStatus(str, Enum):
    PENDING = 'Pending'
    PREPARING = 'Preparing'
    RUNNING = 'Running'
    COMPLETED = 'Completed'
    FAILED = 'Failed'
    CANCELLED = 'Cancelled'


TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.PREPARING, TaskStatus.CANCELLED},
    TaskStatus.PREPARING: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(), TaskStatus.FAILED: set(), TaskStatus.CANCELLED: set(),
}


@dataclass
class TaskRecord:
    plan: OperationPlan
    id: str = field(default_factory=lambda: uuid4().hex)
    status: TaskStatus = TaskStatus.PENDING
    progress: Progress = field(default_factory=Progress)
    command: tuple[str, ...] = ()
    log: str = ''
    error: str = ''
    partial_path: Path | None = None
    result: MediaFile | None = None
    failure_detail: str = ''
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: float | None = None
    cancel_requested: bool = False
    pass_index: int = 0
    pass_count: int = 1
    commands: tuple[tuple[str, ...], ...] = ()
    source_fingerprint: tuple[int, int] | None = None
    binary_version: str = ''
    _started_clock: float | None = field(default=None, repr=False, compare=False)

    @property
    def elapsed(self) -> float | None:
        if self.finished_at is not None:
            return self.elapsed_seconds
        return monotonic() - self._started_clock if self._started_clock is not None else None

    def transition(self, status: TaskStatus) -> None:
        if status not in TRANSITIONS[self.status]:
            raise ValueError(f'Illegal task transition: {self.status.value} -> {status.value}')
        if status == TaskStatus.PREPARING:
            self.started_at = datetime.now(UTC).isoformat()
            self._started_clock = monotonic()
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            self.elapsed_seconds = self.elapsed if self._started_clock is not None else 0.0
            self.finished_at = datetime.now(UTC).isoformat()
        self.status = status

    def append_log(self, text: str) -> None:
        self.log = (self.log + text)[-16000:]
