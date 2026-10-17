"""Editable starting points, not machine capability claims."""
from dataclasses import dataclass

from media_wrapper.domain.remux import Container


@dataclass(frozen=True)
class EncodingPreset:
    name: str
    video_encoder: str | None
    container: Container
    crf: int
    speed: str
    audio_bitrate: int


PRESETS = (
    EncodingPreset('Quality H.264 MP4', 'libx264', Container.MP4, 20, 'medium', 192000),
    EncodingPreset('Efficient H.265 MP4', 'libx265', Container.MP4, 28, 'slow', 128000),
    EncodingPreset('Audio-only AAC MP4', None, Container.MP4, 23, 'medium', 192000),
)
