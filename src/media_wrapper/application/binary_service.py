"""Binary detection use case."""
from pathlib import Path

from media_wrapper.application.errors import use_case
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries, resolve


@use_case('Binary detection')
def detect_binaries(mode: str, directory: str | Path | None) -> Binaries:
    return resolve(mode, directory)
