"""Immutable, Qt-independent operation plans. No filesystem access."""
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path

from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.remux import Container


class MediaOperation(str, Enum):
    REMUX = 'remux'
    CONVERT = 'convert'
    COMPRESS = 'compress'


class ValidationCode(str, Enum):
    INPUT = 'input'
    OUTPUT = 'output'
    STREAM = 'stream'
    COMPATIBILITY = 'compatibility'
    OPTION = 'option'


class PlanValidationError(ValueError):
    def __init__(self, code: ValidationCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EncodingProfile:
    encoder: str = 'copy'
    bitrate: int | None = None
    width: int | None = None
    height: int | None = None
    fps: Fraction | None = None
    crf: int | None = None
    preset: str | None = None
    audio_quality: int | None = None


@dataclass(frozen=True)
class StreamSelection:
    index: int
    profile: EncodingProfile = EncodingProfile()


@dataclass(frozen=True)
class OutputTarget:
    path: Path
    container: Container
    temporary_path: Path | None = None

    @property
    def execution_path(self) -> Path:
        return self.temporary_path if self.temporary_path is not None else self.path


@dataclass(frozen=True)
class OperationPlan:
    operation: MediaOperation
    media: MediaFile
    streams: tuple[StreamSelection, ...]
    output: OutputTarget
    target_size_bytes: int | None = None
    two_pass: bool = False
    hardware_device: str | None = None
    hardware_note: str = ''
