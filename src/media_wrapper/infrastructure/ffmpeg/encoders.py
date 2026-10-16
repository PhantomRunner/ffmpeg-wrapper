"""Read the selected build's encoder list on a worker; no availability assumptions."""
from pathlib import Path
from threading import Event

from media_wrapper.infrastructure.ffmpeg.probe_service import run_cancellable_probe


def parse_encoders(text: str) -> frozenset[str]:
    result = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in 'VAS' and parts[1] != '=':
            result.add(parts[1])
    return frozenset(result)


def list_encoders(ffmpeg: Path, cancel_event: Event) -> frozenset[str]:
    result = run_cancellable_probe([str(ffmpeg), '-hide_banner', '-encoders'], cancel_event)
    if result.returncode:
        raise RuntimeError(f'Encoder discovery failed: {result.stderr}')
    return parse_encoders(result.stdout)
