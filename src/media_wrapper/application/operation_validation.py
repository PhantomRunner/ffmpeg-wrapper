"""Filesystem validation and application-facing plan policy exports."""
from media_wrapper.domain.operation_policy import fail, validate_plan
from media_wrapper.domain.operations import OperationPlan, ValidationCode

__all__ = ['validate_paths', 'validate_plan']


def validate_paths(plan: OperationPlan) -> None:
    """Recheck immediately before execution; FFmpeg -n also guards its output."""
    source = plan.media.path
    if not source.is_file():
        fail(ValidationCode.INPUT, 'Source must be an existing file')
    for target in (plan.output.path, plan.output.temporary_path):
        if target is None:
            continue
        if source.resolve() == target.resolve() or (target.exists() and source.samefile(target)):
            fail(ValidationCode.OUTPUT, 'Source and destination must differ')
        if target.exists() or target.is_symlink():
            fail(ValidationCode.OUTPUT, 'Destination already exists; choose a new filename')
        if not target.parent.is_dir():
            fail(ValidationCode.OUTPUT, 'Destination directory does not exist')
        # Reject names invalid on Windows even when planning on Linux.
        name = target.name
        if any(c in name for c in '<>:"/\\|?*') or any(ord(c) < 32 for c in name) or name.endswith((' ', '.')):
            fail(ValidationCode.OUTPUT, 'Destination filename is not portable')
        if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            fail(ValidationCode.OUTPUT, 'Destination filename is reserved on Windows')
