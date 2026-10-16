"""Pure, typed FFmpeg command construction. Never creates shell strings."""
from pathlib import Path

from media_wrapper.domain.remux import Container, RemuxRequest


def build_remux_command(ffmpeg: Path, request: RemuxRequest) -> list[str]:
    if not isinstance(request.container, Container):
        raise TypeError('Unsupported container')
    if not request.streams or any(s.index < 0 for s in request.streams):
        raise ValueError('Select at least one valid stream')
    if len({s.index for s in request.streams}) != len(request.streams):
        raise ValueError('Duplicate stream selection')
    if request.source.resolve() == request.destination.resolve():
        raise ValueError('Source and destination must differ')
    args = [str(ffmpeg), '-hide_banner', '-nostdin', '-n', '-i', str(request.source.absolute())]
    for stream in request.streams:
        args.extend(['-map', f'0:{stream.index}'])
    args.extend(['-c', 'copy', '-f', request.container.value, str(request.destination.absolute())])
    return args
