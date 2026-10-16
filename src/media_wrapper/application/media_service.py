"""Inspection and remux validation, independent of Qt."""
from pathlib import Path

from media_wrapper.application.errors import use_case
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.remux import Container, RemuxRequest, Stream
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.command_builder import build_remux_command
from media_wrapper.infrastructure.ffmpeg.probe_service import inspect_media

# Intentionally limited first slice; unlisted codecs require a later policy update.
_ALLOWED = {
    Container.MP4: {'video': {'h264', 'hevc', 'av1', 'mpeg4'},
                    'audio': {'aac', 'mp3', 'ac3', 'eac3', 'alac'},
                    'subtitle': {'mov_text'}},
    Container.MATROSKA: {'video': {'h264', 'hevc', 'av1', 'vp8', 'vp9', 'mpeg4', 'mpeg2video', 'ffv1'},
                         'audio': {'aac', 'mp3', 'ac3', 'eac3', 'flac', 'opus', 'vorbis', 'pcm_s16le'},
                         'subtitle': {'subrip', 'ass', 'ssa', 'webvtt', 'hdmv_pgs_subtitle', 'dvd_subtitle'}},
}


class MediaService:
    def __init__(self, binaries: Binaries) -> None:
        self.binaries = binaries

    @use_case('Inspection')
    def inspect(self, source: Path) -> MediaFile:
        return inspect_media(self.binaries.ffprobe, source)

    @use_case('Remux preparation')
    def prepare_remux(self, source: Path, destination: Path, container: Container) -> list[str]:
        source, destination = validate_remux_paths(source, destination, container)
        info = self.inspect(source)
        if any(s.index is None for s in info.streams):
            raise ValueError('Cannot remux streams without indices; inspect with a working FFprobe build')
        streams = tuple(Stream(s.index, s.kind, s.codec) for s in info.streams if s.index is not None)
        if not streams:
            raise ValueError('Source has no streams')
        for stream in streams:
            if stream.codec not in _ALLOWED[container].get(stream.kind, set()):
                raise ValueError(f'Stream {stream.index}: {stream.kind}/{stream.codec} is not supported by the initial {container.value} remux policy')
        return build_remux_command(self.binaries.ffmpeg, RemuxRequest(source, destination, container, streams))


@use_case('Remux validation')
def validate_remux_paths(source: Path, destination: Path, container: Container) -> tuple[Path, Path]:
    source, destination = source.expanduser().absolute(), destination.expanduser().absolute()
    if not source.is_file():
        raise ValueError('Source must be an existing file')
    if source.resolve() == destination.resolve() or (destination.exists() and source.samefile(destination)):
        raise ValueError('Source and destination must differ')
    if destination.exists() or destination.is_symlink():
        raise ValueError('Destination already exists; choose a new filename')
    if not destination.parent.is_dir():
        raise ValueError('Destination directory does not exist')
    expected = {Container.MATROSKA: '.mkv', Container.MP4: '.mp4'}[container]
    if destination.suffix.lower() != expected:
        raise ValueError(f'Destination must use {expected}')
    return source, destination
