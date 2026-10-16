"""Desktop presentation state, independent of Qt widgets."""
from dataclasses import dataclass, field
from pathlib import Path

from media_wrapper.domain.inspection import InspectionRecord
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.remux import Container
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
    destination: str = ''
    container: Container = Container.MATROSKA
    form_error: str = 'Inspect a file first.'
    command: tuple[str, ...] = ()
    media: MediaFile | None = None
    selected_streams: tuple[int, ...] = ()
    inspections: dict[Path, InspectionRecord] = field(default_factory=dict)
    stream_selections: dict[Path, tuple[int, ...]] = field(default_factory=dict)
    inspection_active: bool = False
    cancel_requested: bool = False
    inspection_summary: str = ''
