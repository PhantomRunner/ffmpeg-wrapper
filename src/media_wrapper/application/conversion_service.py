"""Translate typed UI choices into domain plans; validate/probe only on workers."""
from fractions import Fraction
from threading import Event

from media_wrapper.application.hardware_selection import select_hardware
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_service import prepare_operation
from media_wrapper.domain.capabilities import CapabilityReport
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.custom_options import parse_custom_options
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import (
    EncodingProfile,
    OperationPlan,
    OutputTarget,
    StreamSelection,
)
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders


def conversion_plan(media: MediaFile, request: ConversionRequest, report: CapabilityReport | None = None) -> OperationPlan:
    if request.mode not in {'default', 'quality', 'bitrate', 'target'}:
        raise ValueError('Unsupported rate control mode')
    if request.mode == 'target' and request.target_size_bytes is None:
        raise ValueError('Specify a target file size')
    sources = {s.index: s for s in media.streams}
    streams = []
    fps = Fraction(request.fps) if request.fps.strip() else None
    for index, encoder in request.tracks:
        if encoder == 'omit':
            continue
        if index not in sources:
            raise ValueError(f'Stream {index} no longer exists')
        kind = sources[index].kind
        profile = EncodingProfile(encoder)
        if encoder != 'copy':
            profile = EncodingProfile(encoder, (request.audio_bitrate if request.audio_quality is None else None) if encoder == 'aac' else (request.video_bitrate if kind == 'video' and request.mode in {'bitrate', 'target'} else None),
                                      request.width if kind == 'video' else None,
                                      request.height if kind == 'video' else None,
                                      fps if kind == 'video' else None,
                                      request.crf if kind == 'video' and request.mode == 'quality' else None,
                                      request.preset if kind == 'video' and request.mode != 'default' else None,
                                      request.audio_quality if encoder == 'aac' else None)
        elif kind == 'video' and any(v is not None for v in (request.width, request.height, fps)):
            raise ValueError('Choose a video encoder to change resolution or FPS')
        streams.append(StreamSelection(index, profile))
    if request.track_order:
        by_index = {s.index: s for s in streams}
        if len(request.track_order) != len(streams) or set(request.track_order) != set(by_index):
            raise ValueError('Track order must list every selected stream index exactly once')
        streams = [by_index[i] for i in request.track_order]
    plan = OperationPlan(request.operation, media, tuple(streams),
                         OutputTarget(request.destination.expanduser().absolute(), request.container),
                         request.target_size_bytes if request.mode == 'target' else None,
                         metadata_policy=request.metadata_policy, chapter_policy=request.chapter_policy,
                         custom_options=parse_custom_options(request.custom_arguments))
    return select_hardware(plan, report, request.hardware_mode, request.gpu_encoder)


def preview_conversion(binaries: Binaries, plan: OperationPlan) -> list[list[str]]:
    event = Event()
    media = MediaService(binaries).inspect(plan.media.path, event)
    from dataclasses import replace
    plan = replace(plan, media=media)
    available = list_encoders(binaries.ffmpeg, event)
    prepared = prepare_operation(plan, available_encoders=available)
    prefix = prepared.output.execution_path.with_suffix('.passlog')
    return CommandBuilder().build_passes(binaries.ffmpeg, prepared, available, prefix)


def validate_queue_snapshot(binaries: Binaries, plan: OperationPlan) -> OperationPlan:
    """Refresh and validate immutable intent without reserving or creating output."""
    from dataclasses import replace
    event = Event()
    media = MediaService(binaries).inspect(plan.media.path, event)
    available = list_encoders(binaries.ffmpeg, event)
    return prepare_operation(replace(plan, media=media), staged=False, available_encoders=available)
