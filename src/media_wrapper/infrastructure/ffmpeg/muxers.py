"""Cancellable selected-build muxer discovery, always outside the UI thread."""
from pathlib import Path
from threading import Event

from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.probe_service import run_cancellable_probe


def parse_muxers(text: str) -> frozenset[str]:
    names = set()
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] in ('E', 'DE') and fields[1] != '=':
            names.update(fields[1].split(','))
    return frozenset(names)


def list_muxers(ffmpeg: Path, event: Event) -> frozenset[str]:
    result = run_cancellable_probe([str(ffmpeg), '-hide_banner', '-muxers'], event)
    if result.returncode:
        raise RuntimeError(f'Muxer discovery failed: {result.stderr[-4000:]}')
    return parse_muxers(result.stdout)


def require_muxer(ffmpeg: Path, container: Container, event: Event) -> None:
    muxer = CONTAINERS[container].muxer
    if muxer not in list_muxers(ffmpeg, event):
        raise ValueError(f'Muxer {muxer} is unavailable in the selected FFmpeg build')
