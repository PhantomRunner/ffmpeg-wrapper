"""Read-only draft preparation over existing media, policy and command services."""
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event

from media_wrapper.application.batch_service import path_key
from media_wrapper.application.conversion_service import conversion_plan
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_service import (
    operation_warnings,
    prepare_operation,
)
from media_wrapper.application.validation_preview import (
    FileValidation,
    ValidationCandidate,
    blocked,
)
from media_wrapper.domain.draft import DraftOptions
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    PlanValidationError,
    StreamSelection,
    ValidationCode,
)
from media_wrapper.domain.output_naming import draft_output_name
from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders
from media_wrapper.infrastructure.ffmpeg.muxers import require_muxer


@dataclass(frozen=True)
class DraftInput:
    id: str
    path: Path
    revision: int
    options: DraftOptions | None
    probe_error: str = ''
    already_queued: bool = False
    fingerprint: tuple[int, int] | None = None
    source_id: str | None = None
    operation: MediaOperation | None = None


@dataclass(frozen=True)
class DraftSnapshot:
    revision: int
    operation: MediaOperation
    inputs: tuple[DraftInput, ...]
    sources: tuple[Path, ...]


@dataclass(frozen=True)
class PreparedItem:
    source: DraftInput
    validation: FileValidation
    plan: OperationPlan | None = None
    fingerprint: tuple[int, int] | None = None


@dataclass(frozen=True)
class PreparedDraft:
    snapshot: DraftSnapshot
    items: tuple[PreparedItem, ...]

    @property
    def ready(self):
        return tuple(item for item in self.items if item.plan is not None and item.validation.ready)


def snapshot_draft(draft) -> DraftSnapshot:
    inputs = []
    configurations = (
        ((draft.items[output.source_id], output, output.operation)
         for output in draft.outputs.values() if output.included)
        if draft.multiple_outputs else
        ((item, item, draft.operation) for item in draft.items.values() if item.included)
    )
    for item, configuration, operation in configurations:
        options = configuration.options.get(operation)
        error = ''
        if not item.inspected:
            error = (item.inspection.error or item.inspection.status.value
                     if item.inspection else 'Inspect this source first.')
        inputs.append(DraftInput(configuration.id, item.path, configuration.revision, options, error,
                                 bool(options and configuration.queued.get(operation) == options),
                                 item.fingerprint, item.id, operation))
    return DraftSnapshot(draft.revision, draft.operation, tuple(inputs),
                         tuple(item.path for item in draft.items.values()))


def requested_destination(source: DraftInput, operation, index):
    from media_wrapper.domain.containers import CONTAINERS
    options = source.options
    if options.output_override:
        return Path(options.output_override).expanduser().absolute()
    folder = Path(options.folder).expanduser().absolute() if options.folder.strip() else source.path.parent
    suffix = CONTAINERS[options.request.container].extension
    return folder / draft_output_name(options.template, source.path, operation, index, suffix)


def draft_size_note(media, options):
    """Filesystem-free estimate using the same existing execution/size policies."""
    from media_wrapper.application.size_estimate import (
        estimate_output,
        estimate_plan_size,
    )
    request = options.request
    if request.operation != MediaOperation.REMUX:
        return estimate_output(media, request)
    plan = OperationPlan(MediaOperation.REMUX, media, tuple(StreamSelection(i) for i, action in request.tracks if action != 'omit'),
                         OutputTarget(request.destination, request.container))
    size = estimate_plan_size(plan)
    return f'Approximate output: {size / 1048576:.1f} MiB; actual muxing size may differ.' if size is not None else 'Size unknown until encoded.'


def prepare_draft(snapshot: DraftSnapshot, binaries, capabilities=None, reserved=(), event=None) -> PreparedDraft:
    """Run on a worker. Never create outputs, mutate drafts or add queue jobs."""
    event = event or Event()
    destinations, initial_errors = {}, {}
    for index, source in enumerate(snapshot.inputs, 1):
        try:
            if source.probe_error or source.options is None:
                raise PlanValidationError(ValidationCode.INPUT, source.probe_error or 'Inspect this source first.')
            if source.already_queued:
                raise ValueError('These settings were already added to the queue. Change settings to create another job.')
            destinations[source.id] = requested_destination(source, source.operation or snapshot.operation, index)
        except (ValueError, OSError) as error:
            initial_errors[source.id] = error
    fixed = Counter(path_key(destinations[s.id]) for s in snapshot.inputs
                    if s.id in destinations and not s.options.auto_number)
    protected = {path_key(path) for path in (*snapshot.sources, *reserved)}
    allocated = protected | set(fixed)
    directory_keys = {}
    inspections = {}
    results = []
    available = None
    for source in snapshot.inputs:
        operation = source.operation or snapshot.operation
        destination = destinations.get(source.id)
        candidate = ValidationCandidate(source.path, destination,
                                        source.options.request.container.value if source.options else '',
                                        operation.value, lambda: None)
        try:
            if event.is_set():
                raise ValueError('Validation cancelled. Validate again before processing.')
            if source.id in initial_errors:
                raise initial_errors[source.id]
            directory = destination.parent
            if directory not in directory_keys:
                if not directory.is_dir():
                    raise PlanValidationError(ValidationCode.OUTPUT, 'Choose an existing output folder.')
                directory_keys[directory] = {path_key(path) for path in directory.iterdir()}
            existing = directory_keys[directory]
            key = path_key(destination)
            if source.options.auto_number:
                original, number = destination, 1
                while key in allocated or key in existing:
                    destination = original.with_name(f'{original.stem}_{number}{original.suffix}')
                    key, number = path_key(destination), number + 1
            elif key in protected or key in existing or fixed[key] > 1:
                raise PlanValidationError(ValidationCode.OUTPUT,
                                          'Output collides with a source, queued destination, existing file or another draft output. Choose a name or enable auto-numbering.')
            allocated.add(key)
            candidate = replace(candidate, destination=destination)
            request = replace(source.options.request, destination=destination)
            require_muxer(binaries.ffmpeg, request.container, event)
            before = source.path.stat()
            if source.fingerprint is not None and source.fingerprint != (before.st_size, before.st_mtime_ns):
                raise PlanValidationError(ValidationCode.INPUT, 'Source changed since inspection. Inspect it again before processing.')
            fingerprint = (before.st_size, before.st_mtime_ns)
            key = source.path, fingerprint
            if key not in inspections:
                inspections[key] = MediaService(binaries).inspect(source.path, event)
            media = inspections[key]
            if any(stream.index is None for stream in media.streams):
                raise PlanValidationError(ValidationCode.STREAM, 'FFprobe returned a stream without an index. Inspect this source with a working FFprobe before processing.')
            after = source.path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise PlanValidationError(ValidationCode.INPUT, 'Source changed during validation. Inspect it again.')
            if operation == MediaOperation.REMUX:
                if any(action not in ('copy', 'omit') for _, action in request.tracks):
                    raise PlanValidationError(ValidationCode.OPTION, 'Remux must copy every included stream.')
                mapped = tuple(i for i, action in request.tracks if action != 'omit')
                if request.track_order and (len(request.track_order) != len(mapped)
                                            or set(request.track_order) != set(mapped)):
                    raise PlanValidationError(ValidationCode.STREAM, 'Track order must list every copied stream.')
                plan = OperationPlan(MediaOperation.REMUX, media,
                                     tuple(StreamSelection(i) for i in (request.track_order or mapped)),
                                     OutputTarget(destination, request.container),
                                     metadata_policy=request.metadata_policy, chapter_policy=request.chapter_policy,
                                     deep_verify=request.deep_verify)
            else:
                plan = conversion_plan(media, request, capabilities)
            plan = replace(plan, source_id=source.source_id, output_id=source.id)
            if available is None:
                available = list_encoders(binaries.ffmpeg, event)
            validated = prepare_operation(plan, staged=False, available_encoders=available)
            preview = prepare_operation(validated, available_encoders=available)
            commands = CommandBuilder().build_passes(binaries.ffmpeg, preview, available,
                                                     preview.output.execution_path.with_suffix('.passlog'))
            excluded = {index for index, action in request.tracks if action == 'omit'}
            warnings = list(operation_warnings(validated))
            if excluded:
                warnings.append('Excluded tracks: ' + ', '.join(
                    f'#{track.index} {track.title or track.kind}' for track in media.streams if track.index in excluded))
            validation = FileValidation(source.path, destination, request.container.value,
                                        operation.value,
                                        tuple(f'Stream {s.index}: {s.profile.encoder}' for s in validated.streams),
                                        warnings=tuple(warnings),
                                        commands=tuple(tuple(c) for c in commands))
            results.append(PreparedItem(source, validation, validated, (after.st_size, after.st_mtime_ns)))
        except Exception as error:  # noqa: BLE001 - per-source isolation is intentional
            results.append(PreparedItem(source, blocked(candidate, error)))
    return PreparedDraft(snapshot, tuple(results))
