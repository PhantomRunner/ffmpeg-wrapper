"""Immutable media metadata; independent of Qt and FFprobe's JSON shape."""
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class MediaStream:
    index: int | None
    kind: str = 'unknown'
    codec: str = 'unknown'
    codec_long_name: str | None = None
    language: str | None = None
    title: str | None = None
    bit_rate: int | None = None
    width: int | None = None
    height: int | None = None
    average_frame_rate: Fraction | None = None
    nominal_frame_rate: Fraction | None = None
    sample_rate: int | None = None
    channels: int | None = None
    channel_layout: str | None = None

    @property
    def frame_rate(self) -> Fraction | None:
        return self.average_frame_rate or self.nominal_frame_rate


@dataclass(frozen=True)
class MediaChapter:
    start: float | None
    end: float | None
    title: str | None = None


@dataclass(frozen=True)
class MediaFile:
    path: Path
    format_name: str = 'unknown'
    duration: float | None = None
    size_bytes: int | None = None
    streams: tuple[MediaStream, ...] = ()
    bit_rate: int | None = None
    tags: tuple[tuple[str, str], ...] = ()
    chapters: tuple[MediaChapter, ...] = ()
