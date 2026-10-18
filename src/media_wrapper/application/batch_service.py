"""All-or-nothing batch planning with portable output naming and collisions."""
from dataclasses import replace
from pathlib import Path
from string import Formatter
from threading import Event

from media_wrapper.application.conversion_service import conversion_plan
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_service import prepare_operation
from media_wrapper.domain.capabilities import CapabilityReport
from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.operations import OperationPlan
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders
from media_wrapper.infrastructure.ffmpeg.muxers import require_muxer


def path_key(path: Path) -> str:
    # Also reject names that would collide on Windows while planning on Linux.
    return str(path.resolve()).casefold()


def output_name(template: str, source: Path, index: int, suffix: str) -> str:
    if not template or len(template) > 256:
        raise ValueError('Supply a filename template of at most 256 characters')
    for _, field, spec, conversion in Formatter().parse(template):
        if field is not None and (field not in {'stem', 'index', 'ext'} or spec or conversion):
            raise ValueError('Templates support only {stem}, {index}, {ext}; no format expressions')
    name = template.format(stem=source.stem, index=index, ext=suffix)
    if not name or '/' in name or '\\' in name or Path(name).name != name:
        raise ValueError('Template must produce a filename, not a directory or path')
    return name


def plan_batch(paths: tuple[Path, ...], request: ConversionRequest, directory: Path, template: str,
               binaries: Binaries, report: CapabilityReport | None, reserved: tuple[Path, ...] = ()) -> tuple[OperationPlan, ...]:
    if not paths or len(paths) > 1000 or len(set(paths)) != len(paths):
        raise ValueError('Choose 1–1000 distinct input files')
    directory = directory.expanduser().absolute()
    if not directory.is_dir():
        raise ValueError('Choose an existing output folder')
    keys = {path_key(p) for p in (*paths, *reserved, *directory.iterdir())}
    require_muxer(binaries.ffmpeg, request.container, Event())
    available = list_encoders(binaries.ffmpeg, Event())
    plans = []
    suffix = CONTAINERS[request.container].extension
    for index, path in enumerate(paths, 1):
        destination = directory / output_name(template, path, index, suffix)
        key = path_key(destination)
        if key in keys:
            raise ValueError(f'Batch output collision (source, reserved or existing name): {destination}')
        keys.add(key)
        media = MediaService(binaries).inspect(path)
        plan = conversion_plan(media, replace(request, destination=destination), report)
        # No filesystem mutations: validate the whole batch before enqueuing any job.
        prepare_operation(plan, staged=False, available_encoders=available)
        plans.append(plan)
    return tuple(plans)
