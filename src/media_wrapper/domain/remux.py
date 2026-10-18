"""Qt-independent requests for the initial, conservative remux slice."""
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class Container(str, Enum):
    MATROSKA = 'matroska'
    MP4 = 'mp4'
    MOV = 'mov'
    WEBM = 'webm'
    WAV = 'wav'
    FLAC = 'flac'


@dataclass(frozen=True)
class Stream:
    index: int
    kind: str
    codec: str

    @classmethod
    def from_probe(cls, payload: Mapping[str, Any]) -> 'Stream':
        index = payload.get('index')
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError('FFprobe stream must have a nonnegative integer index')
        return cls(index, str(payload.get('codec_type', 'unknown')),
                   str(payload.get('codec_name', 'unknown')))


@dataclass(frozen=True)
class RemuxRequest:
    source: Path
    destination: Path
    container: Container
    streams: tuple[Stream, ...]
