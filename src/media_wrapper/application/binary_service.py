"""Binary detection use case."""
from pathlib import Path

from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries, resolve


def detect_binaries(mode: str, directory: str | Path | None) -> Binaries:
    return resolve(mode, directory)
