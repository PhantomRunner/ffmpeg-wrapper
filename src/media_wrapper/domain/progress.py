"""Progress estimates, independent of Qt and FFmpeg I/O."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Progress:
    seconds: float | None = None
    percent: float | None = None
    speed: float | None = None
    eta: float | None = None
    ended: bool = False
