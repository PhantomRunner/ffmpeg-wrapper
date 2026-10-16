"""Translate typed UI choices into domain plans; validate/probe only on workers."""
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from threading import Event

from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_service import prepare_operation
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import (
    EncodingProfile,
    MediaOperation,
    OperationPlan,
    OutputTarget,
    StreamSelection,
)
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders


@dataclass(frozen=True)
class ConversionRequest:
    destination: Path
    container: Container
    tracks: tuple[tuple[int, str], ...]
    width: int | None = None
    height: int | None = None
    fps: str = ''
    audio_bitrate: int = 128000


def conversion_plan(media: MediaFile, request: ConversionRequest) -> OperationPlan:
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
            profile = EncodingProfile(encoder, request.audio_bitrate if encoder == 'aac' else None,
                                      request.width if kind == 'video' else None,
                                      request.height if kind == 'video' else None,
                                      fps if kind == 'video' else None)
        elif kind == 'video' and any(v is not None for v in (request.width, request.height, fps)):
            raise ValueError('Choose a video encoder to change resolution or FPS')
        streams.append(StreamSelection(index, profile))
    return OperationPlan(MediaOperation.CONVERT, media, tuple(streams),
                         OutputTarget(request.destination.expanduser().absolute(), request.container))


def preview_conversion(binaries: Binaries, plan: OperationPlan) -> list[str]:
    event = Event()
    media = MediaService(binaries).inspect(plan.media.path, event)
    from dataclasses import replace
    plan = replace(plan, media=media)
    available = list_encoders(binaries.ffmpeg, event)
    prepared = prepare_operation(plan, available_encoders=available)
    return CommandBuilder().build(binaries.ffmpeg, prepared, available, progress=True)
