"""Desktop presentation state, independent of Qt widgets."""
from dataclasses import dataclass
from pathlib import Path

from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries


@dataclass
class DesktopState:
    binaries: Binaries | None = None
    source: Path | None = None
    busy: bool = False
    status: str = 'FFmpeg not detected'
    output: str = ''
    files: tuple[Path, ...] = ()
    current_file: Path | None = None
    recent_destination: Path | None = None
