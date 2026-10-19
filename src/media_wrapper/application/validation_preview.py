"""Read-only per-file validation reports shared by single and future bulk workflows."""
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from media_wrapper.application.batch_service import path_key
from media_wrapper.application.conversion_service import preview_conversion
from media_wrapper.application.errors import normalize_error
from media_wrapper.domain.operations import (
    OperationPlan,
    PlanValidationError,
    ValidationCode,
)
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries


@dataclass(frozen=True)
class ValidationCandidate:
    source: Path | None
    destination: Path | None
    container: str
    operation: str
    build_plan: Callable[[], OperationPlan]


@dataclass(frozen=True)
class FileValidation:
    source: Path | None
    destination: Path | None
    container: str
    operation: str
    streams: tuple[str, ...] = ()
    error: str = ''
    field: str = ''
    advice: str = ''
    warnings: tuple[str, ...] = ()
    commands: tuple[tuple[str, ...], ...] = ()

    @property
    def ready(self) -> bool:
        return not self.error


@dataclass(frozen=True)
class ValidationReport:
    files: tuple[FileValidation, ...]

    @property
    def summary(self) -> str:
        ready = sum(file.ready for file in self.files)
        warnings = sum(bool(file.warnings) for file in self.files)
        return f'Ready: {ready} · Warnings: {warnings} · Blocked: {len(self.files) - ready}'


def blocked(candidate: ValidationCandidate, error: Exception) -> FileValidation:
    cause = error
    while cause.__cause__ is not None:
        cause = cause.__cause__
    field = cause.code.value if isinstance(cause, PlanValidationError) else 'settings'
    advice = {
        'input': 'Select an existing source and inspect it again.',
        'output': 'Choose a new filename in an existing writable folder with the container extension.',
        'stream': 'Review the selected stream indices; select at least one supported stream.',
        'compatibility': 'Choose a compatible container or encoder, or explicitly omit the incompatible stream.',
        'option': 'Review encoder, quality, bitrate and format settings; check available encoders in Settings.',
        'settings': 'Review the reported setting and selected FFmpeg build, then validate again.',
    }[field]
    message = str(cause) if isinstance(cause, (ValueError, OSError)) else str(normalize_error('Validation', error))
    return FileValidation(candidate.source, candidate.destination, candidate.container,
                          candidate.operation, error=message, field=field, advice=advice)


def validate_candidates(candidates: tuple[ValidationCandidate, ...], binaries: Binaries,
                        reserved: tuple[Path, ...] = ()) -> ValidationReport:
    """Call on a worker. No output creation and no queue mutations."""
    keys = Counter(path_key(c.destination) for c in candidates if c.destination)
    protected = {path_key(p) for p in reserved}
    protected.update(path_key(c.source) for c in candidates if c.source)
    results = []
    for candidate in candidates:
        plan = None
        try:
            if candidate.destination:
                key = path_key(candidate.destination)
                if keys[key] > 1 or key in protected:
                    raise PlanValidationError(ValidationCode.OUTPUT, 'Output collides with another source, batch output or queued destination.')
            plan = candidate.build_plan()
            commands = preview_conversion(binaries, plan)
            warnings = (plan.hardware_note,) if plan.hardware_note else ()
            results.append(FileValidation(
                candidate.source, plan.output.path, candidate.container, plan.operation.value,
                tuple(f'Stream {s.index}: {s.profile.encoder}' for s in plan.streams),
                warnings=warnings, commands=tuple(tuple(command) for command in commands)))
        except Exception as error:  # noqa: BLE001 - each candidate has its own failure result
            result = blocked(candidate, error)
            if plan:
                from dataclasses import replace
                result = replace(result, streams=tuple(f'Stream {s.index}: {s.profile.encoder}' for s in plan.streams))
            results.append(result)
    return ValidationReport(tuple(results))
