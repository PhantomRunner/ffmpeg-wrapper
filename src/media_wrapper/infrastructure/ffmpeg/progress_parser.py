"""Incremental bounded parser for FFmpeg -progress pipe:1 records."""
import math

from media_wrapper.domain.progress import Progress


def number(value: str | None) -> float | None:
    try:
        result = float(value) if value is not None else None
        return result if result is not None and math.isfinite(result) and result >= 0 else None
    except ValueError:
        return None


class ProgressParser:
    def __init__(self, duration: float | None = None) -> None:
        self.duration = duration if duration is not None and math.isfinite(duration) and duration > 0 else None
        self.buffer = b''
        self.values: dict[str, str] = {}

    def feed(self, data: bytes) -> list[Progress]:
        self.buffer += data
        result = []
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            key, sep, value = line.decode('ascii', errors='replace').strip().partition('=')
            if sep and key in {'out_time_us', 'out_time_ms', 'speed', 'progress'}:
                self.values[key] = value
            if key == 'progress' and sep:
                # Both FFmpeg fields are microseconds despite the historical ms name.
                microseconds = number(self.values.get('out_time_us', self.values.get('out_time_ms')))
                seconds = microseconds / 1_000_000 if microseconds is not None else None
                speed = number(self.values.get('speed', '').removesuffix('x'))
                percent = min(100.0, seconds / self.duration * 100) if seconds is not None and self.duration else None
                eta = max(0.0, self.duration - seconds) / speed if self.duration and seconds is not None and speed else None
                result.append(Progress(seconds, percent, speed, eta, value == 'end'))
                self.values.clear()
        self.buffer = self.buffer[-4096:]
        return result
