"""Typed user choices shared by forms, profile files and application services."""
from dataclasses import dataclass
from pathlib import Path

from media_wrapper.domain.operations import MediaOperation, PreservationPolicy
from media_wrapper.domain.remux import Container


@dataclass(frozen=True)
class ConversionRequest:
    destination: Path
    container: Container
    tracks: tuple[tuple[int, str], ...]
    width: int | None = None
    height: int | None = None
    fps: str = ''
    audio_bitrate: int = 128000
    mode: str = 'default'
    crf: int = 23
    video_bitrate: int = 2000000
    preset: str = 'medium'
    audio_quality: int | None = None
    operation: MediaOperation = MediaOperation.CONVERT
    target_size_bytes: int | None = None
    hardware_mode: str = 'CPU'
    gpu_encoder: str = 'auto'
    track_order: tuple[int, ...] = ()
    metadata_policy: PreservationPolicy = PreservationPolicy.PRESERVE
    chapter_policy: PreservationPolicy = PreservationPolicy.PRESERVE

