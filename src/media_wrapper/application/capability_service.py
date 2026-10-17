"""Describe build support separately from runtime-tested GPU capability."""
from pathlib import Path
from threading import Event

from media_wrapper.domain.capabilities import (
    GPU_ENCODERS, CapabilityReport, EncoderCapability, EncoderStatus,
)
from media_wrapper.infrastructure.ffmpeg.capabilities import discover_build
from media_wrapper.infrastructure.ffmpeg.gpu_probe import test_gpu_encoder


def scan_capabilities(ffmpeg: Path, event: Event, *, refresh: bool = False, test_gpu: bool = False, device: str | None = None) -> CapabilityReport:
    build = discover_build(ffmpeg, event, refresh=refresh)
    gpu = tuple(EncoderCapability(name, name in build.encoders,
                                 EncoderStatus.LISTED if name in build.encoders else EncoderStatus.UNAVAILABLE,
                                 'Not runtime tested' if name in build.encoders else 'Not listed by this FFmpeg build')
                for name in GPU_ENCODERS)
    if test_gpu:
        gpu = tuple(test_gpu_encoder(ffmpeg, c.name, event, device) if c.listed else c for c in gpu)
    return CapabilityReport(build, gpu)
