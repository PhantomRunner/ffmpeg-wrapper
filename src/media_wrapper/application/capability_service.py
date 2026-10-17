"""Describe build support separately from runtime-tested GPU capability."""
from pathlib import Path
from threading import Event

from media_wrapper.domain.capabilities import (
    GPU_ENCODERS, CapabilityReport, EncoderCapability, EncoderStatus,
)
from media_wrapper.infrastructure.ffmpeg.capabilities import discover_build


def scan_capabilities(ffmpeg: Path, event: Event, *, refresh: bool = False) -> CapabilityReport:
    build = discover_build(ffmpeg, event, refresh=refresh)
    gpu = tuple(EncoderCapability(name, name in build.encoders,
                                 EncoderStatus.LISTED if name in build.encoders else EncoderStatus.UNAVAILABLE,
                                 'Not runtime tested' if name in build.encoders else 'Not listed by this FFmpeg build')
                for name in GPU_ENCODERS)
    return CapabilityReport(build, gpu)
