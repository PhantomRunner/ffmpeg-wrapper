"""Task lifecycle and legal transitions, independent of Qt."""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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

    def transition(self, status: TaskStatus) -> None:
        if status not in TRANSITIONS[self.status]:
            raise ValueError(f'Illegal task transition: {self.status.value} -> {status.value}')
        self.status = status

    def append_log(self, text: str) -> None:
        self.log = (self.log + text)[-16000:]
