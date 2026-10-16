"""Qt-independent media metadata entities."""
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

Number = TypeVar('Number', int, float)


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    format_name: str
    duration: float | None
    size_bytes: int | None
    streams: tuple[dict[str, Any], ...]

    @classmethod
    def from_probe(cls, path: Path, payload: dict[str, Any]) -> "MediaInfo":
        fmt = payload.get("format", {})
        streams = payload.get("streams", [])
        if fmt is None:
            fmt = {}
        if streams is None:
            streams = []
        if not isinstance(fmt, dict) or not isinstance(streams, list) or any(not isinstance(s, dict) for s in streams):
            raise ValueError("Invalid FFprobe metadata structure")
        def number(value: Any, cast: type[Number]) -> Number | None:
            try:
                result = cast(value) if value is not None and not isinstance(value, bool) else None
                return result if result is not None and math.isfinite(result) and result >= 0 else None
            except (ValueError, TypeError, OverflowError):
                return None
        return cls(path=path, format_name=str(fmt.get("format_name", "unknown")),
                   duration=number(fmt.get("duration"), float),
                   size_bytes=number(fmt.get("size"), int),
                   streams=tuple(streams))
