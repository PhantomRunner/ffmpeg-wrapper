"""Inspection and remux validation, independent of Qt."""
from pathlib import Path
from threading import Event

from media_wrapper.application.errors import use_case
from media_wrapper.application.operation_service import prepare_command
from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    PreservationPolicy,
    StreamSelection,
)
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.muxers import require_muxer
from media_wrapper.infrastructure.ffmpeg.probe_service import inspect_media


class MediaService:
    def __init__(self, binaries: Binaries) -> None:
        self.binaries = binaries

    @use_case('Inspection')
    def inspect(self, source: Path, cancel_event: Event | None = None) -> MediaFile:
        if cancel_event is None:
            return inspect_media(self.binaries.ffprobe, source)
        return inspect_media(self.binaries.ffprobe, source, cancel_event)

    @use_case('Remux preparation')
    def prepare_remux(self, source: Path, destination: Path, container: Container, indices: tuple[int, ...] | None = None, metadata_policy: PreservationPolicy = PreservationPolicy.PRESERVE, chapter_policy: PreservationPolicy = PreservationPolicy.PRESERVE) -> list[str]:
        source, destination = validate_remux_paths(source, destination, container)
        require_muxer(self.binaries.ffmpeg, container, Event())
        info = self.inspect(source)
        if any(s.index is None for s in info.streams):
            raise ValueError('Cannot remux streams without indices; inspect with a working FFprobe build')
        plan = OperationPlan(MediaOperation.REMUX, info,
                             tuple(StreamSelection(i) for i in (indices if indices is not None else tuple(s.index for s in info.streams if s.index is not None))),
                             OutputTarget(destination, container), metadata_policy=metadata_policy, chapter_policy=chapter_policy)
        # Legacy UI runner writes directly; staged publication arrives in M4/M5.
        return prepare_command(self.binaries.ffmpeg, plan, staged=False)[1]



@use_case('Remux validation')
def validate_remux_paths(source: Path, destination: Path, container: Container) -> tuple[Path, Path]:
    source, destination = source.expanduser().absolute(), destination.expanduser().absolute()
    if not source.is_file():
        raise ValueError('Source must be an existing file')
    if source.resolve() == destination.resolve() or (destination.exists() and source.samefile(destination)):
        raise ValueError('Source and destination must differ')
    if destination.exists() or destination.is_symlink():
        raise ValueError('Destination already exists; choose a new filename')
    if not destination.parent.is_dir():
        raise ValueError('Destination directory does not exist')
    expected = CONTAINERS[container].extension
    if destination.suffix.lower() != expected:
        raise ValueError(f'Destination must use {expected}')
    return source, destination
