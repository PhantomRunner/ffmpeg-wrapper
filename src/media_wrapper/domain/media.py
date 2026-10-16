"""Qt-independent media metadata entities."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    format_name: str
    duration: float | None
    size_bytes: int | None
    streams: tuple[dict[str, Any], ...]

    @classmethod
    def from_probe(cls, path: Path, payload: dict[str, Any]) -> "MediaInfo":
        fmt = payload.get("format") or {}
        def number(value: Any, cast: type) -> Any:
            try:
                return cast(value) if value is not None else None
            except (ValueError, TypeError, OverflowError):
                return None
        return cls(path=path, format_name=str(fmt.get("format_name", "unknown")),
                   duration=number(fmt.get("duration"), float),
                   size_bytes=number(fmt.get("size"), int),
                   streams=tuple(payload.get("streams") or ()))
