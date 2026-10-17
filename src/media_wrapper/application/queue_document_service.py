"""Save intent and revalidate an entire imported queue before adding any jobs."""
from pathlib import Path
from threading import Event

from media_wrapper.application.batch_service import path_key
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_service import prepare_operation
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import OperationPlan
from media_wrapper.domain.queue_document import parse_definition, plan_payload, queue_entries
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders
from media_wrapper.infrastructure.json_documents import read_document, write_document


def fingerprint(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def save_queue(path: Path, plans: tuple[OperationPlan, ...]) -> Path:
    payload = {'kind': 'media-wrapper-queue', 'version': 1,
               'jobs': [plan_payload(plan, fingerprint(plan.media.path)) for plan in plans]}
    queue_entries(payload)
    write_document(path, payload)
    return path


def load_queue(path: Path, binaries: Binaries, reserved: tuple[Path, ...] = ()) -> tuple[OperationPlan, ...]:
    entries = queue_entries(read_document(path))
    # Parse every definition before inspecting any user-specified file.
    definitions = []
    for entry in entries:
        source = entry.get('source')
        if not isinstance(source, str):
            raise ValueError('Missing queue source')
        placeholder = MediaFile(Path(source), None, None, None, ())
        definitions.append(parse_definition(entry, placeholder))
    keys = {path_key(p) for p in (*reserved, *(plan.media.path for plan in definitions))}
    available = list_encoders(binaries.ffmpeg, Event())
    plans = []
    for entry, definition in zip(entries, definitions, strict=True):
        source = definition.media.path
        if list(fingerprint(source)) != entry['fingerprint']:
            raise ValueError(f'Source changed since queue was saved; inspect and rebuild it: {source}')
        key = path_key(definition.output.path)
        if key in keys:
            raise ValueError(f'Imported queue output collision: {definition.output.path}')
        keys.add(key)
        media = MediaService(binaries).inspect(source)
        if list(fingerprint(source)) != entry['fingerprint']:
            raise ValueError(f'Source changed during queue import: {source}')
        plan = parse_definition(entry, media)
        prepared = prepare_operation(plan, staged=False, available_encoders=available)
        plans.append(prepared)
    return tuple(plans)
