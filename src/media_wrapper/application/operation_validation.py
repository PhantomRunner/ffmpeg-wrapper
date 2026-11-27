"""Filesystem validation and application-facing plan policy exports."""
import os
import shutil
from pathlib import Path

from media_wrapper.domain.operation_policy import fail, validate_plan
from media_wrapper.domain.operations import OperationPlan, ValidationCode

__all__ = ['validate_output_name', 'validate_paths', 'validate_plan']


def validate_output_name(path: Path) -> None:
    # Reject names invalid on Windows even when planning on Linux.
    name = path.name
    if any(c in name for c in '<>:"/\\|?*') or any(ord(c) < 32 for c in name) or name.endswith((' ', '.')):
        fail(ValidationCode.OUTPUT, 'Destination filename is not portable')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        fail(ValidationCode.OUTPUT, 'Destination filename is reserved on Windows')



def validate_paths(plan: OperationPlan) -> None:
    """Recheck immediately before execution; FFmpeg -n also guards its output."""
    targets = [path for path in (plan.output.path, plan.output.temporary_path) if path is not None]
    # Windows device names can appear to exist even when no file was created.
    for target in targets:
        validate_output_name(target)
    if plan.output.temporary_path is not None and plan.output.temporary_path.resolve() == plan.output.path.resolve():
        fail(ValidationCode.OUTPUT, "Temporary and final output must differ")
    source = plan.media.path
    if not source.is_file():
        fail(ValidationCode.INPUT, 'Source must be an existing file')
    for target in targets:
        if source.resolve() == target.resolve() or (target.exists() and source.samefile(target)):
            fail(ValidationCode.OUTPUT, 'Source and destination must differ')
        if target.exists() or target.is_symlink():
            fail(ValidationCode.OUTPUT, 'Destination already exists; choose a new filename')
        if not target.parent.is_dir():
            fail(ValidationCode.OUTPUT, 'Destination directory does not exist or the drive is disconnected')
        if plan.output.directory_identity is not None and path_identity(target.parent) != plan.output.directory_identity:
            fail(ValidationCode.OUTPUT, 'Destination directory changed. Reconnect the intended drive and validate a new job.')
        if not os.access(target.parent, os.W_OK):
            fail(ValidationCode.OUTPUT, 'Destination directory is not writable')

    minimum = _estimate_bytes(plan)
    if minimum is not None and shutil.disk_usage(plan.output.path.parent).free < minimum:
        fail(ValidationCode.OUTPUT, f'Insufficient free space on destination; estimate is {minimum:,} bytes')


def _estimate_bytes(plan: OperationPlan) -> int | None:
    if plan.target_size_bytes is not None:
        return plan.target_size_bytes
    sources = {stream.index: stream for stream in plan.media.streams}
    if plan.media.duration is not None:
        rates = [
            sources[s.index].bit_rate if s.profile.encoder == 'copy' else s.profile.bitrate
            for s in plan.streams
        ]
        if all(rate is not None for rate in rates):
            return int(sum(rates) * plan.media.duration / 8 * 1.02)
    if len(plan.streams) == len(sources) and all(s.profile.encoder == 'copy' for s in plan.streams):
        return plan.media.size_bytes
    return None


def path_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino


def source_identity(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
