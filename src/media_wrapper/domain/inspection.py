"""Qt-independent inspection outcomes."""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from media_wrapper.domain.media import MediaFile


class InspectionStatus(str, Enum):
    PENDING = 'Pending'
    RUNNING = 'Running'
    COMPLETED = 'Completed'
    FAILED = 'Failed'
    CANCELLED = 'Cancelled'


class OperationCancelled(Exception):
    """Cooperative cancellation, distinct from a failed operation."""


@dataclass(frozen=True)
class InspectionRecord:
    path: Path
    status: InspectionStatus
    media: MediaFile | None = None
    error: str | None = None
