"""Translate typed UI choices into domain plans; validate/probe only on workers."""
from dataclasses import replace
from fractions import Fraction
from threading import Event

from media_wrapper.application.hardware_selection import select_hardware
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_service import prepare_operation
from media_wrapper.domain.capabilities import CapabilityReport
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.custom_options import parse_custom_options
from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.operation_policy import (
    BITRATE_ENCODERS,
    SPEED_PRESET_ENCODERS,
)
from media_wrapper.domain.operations import (
    EncodingProfile,
    OperationPlan,
    OutputTarget,
    StreamSelection,
)
from media_wrapper.domain.target_size import size_limit
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders
from media_wrapper.infrastructure.ffmpeg.muxers import require_muxer


def profile_for_stream(request: ConversionRequest, stream: MediaStream, encoder: str) -> EncodingProfile:
    """Derive group defaults before applying an explicit per-stream override."""
    kind = stream.kind
    fps = Fraction(request.fps) if request.fps.strip() else None
    if encoder == 'copy':
        if kind == 'video' and any(v is not None for v in (request.width, request.height, fps)):
            raise ValueError('Choose a video encoder to change resolution or FPS')
        return EncodingProfile()
    if kind == 'audio':
        quality = request.audio_quality if encoder in {'aac', 'libmp3lame'} else None
        bitrate = request.audio_bitrate if encoder in BITRATE_ENCODERS and quality is None else None
        return EncodingProfile(
            encoder, bitrate=bitrate, audio_quality=quality,
            sample_rate=48_000 if encoder == 'libopus' and stream.sample_rate != 48_000 else None,
        )
    if kind != 'video':
        return EncodingProfile(encoder)
    return EncodingProfile(
        encoder, bitrate=request.video_bitrate if request.mode in {'bitrate', 'target'} else None,
        width=request.width, height=request.height, fps=fps,
        crf=request.crf if request.mode == 'quality' else None,
        preset=request.preset if encoder in SPEED_PRESET_ENCODERS and request.mode != 'default' else None,
        codec_profile=request.codec_profile, pixel_format=request.pixel_format,
    )


def conversion_plan(media: MediaFile, request: ConversionRequest, report: CapabilityReport | None = None) -> OperationPlan:
    if request.mode not in {'default', 'quality', 'bitrate', 'target'}:
        raise ValueError('Unsupported rate control mode')
    cap = None
    if request.mode == 'target':
        if request.target_size is not None and request.target_size_bytes is not None:
            raise ValueError('Specify only one target file size')
        cap = size_limit(*request.target_size, media) if request.target_size is not None else request.target_size_bytes
        if cap is None:
            raise ValueError('Specify a target file size')
    sources = {s.index: s for s in media.streams}
    overrides = dict(request.stream_profiles)
    selected = {index for index, encoder in request.tracks if encoder != 'omit'}
    if len(overrides) != len(request.stream_profiles) or not overrides.keys() <= selected:
        raise ValueError('Per-stream options must reference distinct, selected streams')
    streams = []
    for index, encoder in request.tracks:
        if encoder == 'omit':
            continue
        if index not in sources:
            raise ValueError(f'Stream {index} no longer exists')
        profile = overrides.get(index)
        if profile is None:
            profile = profile_for_stream(request, sources[index], encoder)
        elif profile.encoder != encoder:
            raise ValueError(f'Stream {index} options do not match its selected encoder')
        streams.append(StreamSelection(index, profile))
    if request.track_order:
        by_index = {s.index: s for s in streams}
        if len(request.track_order) != len(streams) or set(request.track_order) != set(by_index):
            raise ValueError('Track order must list every selected stream index exactly once')
        streams = [by_index[i] for i in request.track_order]
    plan = OperationPlan(
        request.operation, media, tuple(streams),
        OutputTarget(request.destination.expanduser().absolute(), request.container), cap,
        metadata_policy=request.metadata_policy, chapter_policy=request.chapter_policy,
        custom_options=parse_custom_options(request.custom_arguments), deep_verify=request.deep_verify,
    )
    return select_hardware(plan, report, request.hardware_mode, request.gpu_encoder)


def preview_conversion(binaries: Binaries, plan: OperationPlan) -> list[list[str]]:
    event = Event()
    require_muxer(binaries.ffmpeg, plan.output.container, event)
    media = MediaService(binaries).inspect(plan.media.path, event)
    plan = replace(plan, media=media)
    available = list_encoders(binaries.ffmpeg, event)
    prepared = prepare_operation(plan, available_encoders=available)
    prefix = prepared.output.execution_path.with_suffix('.passlog')
    return CommandBuilder().build_passes(binaries.ffmpeg, prepared, available, prefix)


def validate_queue_snapshot(binaries: Binaries, plan: OperationPlan) -> OperationPlan:
    """Refresh and validate immutable intent without reserving or creating output."""
    event = Event()
    require_muxer(binaries.ffmpeg, plan.output.container, event)
    media = MediaService(binaries).inspect(plan.media.path, event)
    available = list_encoders(binaries.ffmpeg, event)
    return prepare_operation(replace(plan, media=media), staged=False, available_encoders=available)
