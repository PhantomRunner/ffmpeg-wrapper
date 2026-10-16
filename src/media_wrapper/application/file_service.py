"""Local file selection validation, without Qt or dialog dependencies."""
from collections.abc import Iterable
from pathlib import Path

from media_wrapper.application.errors import use_case


@use_case('File selection')
def validate_files(paths: Iterable[Path]) -> tuple[Path, ...]:
    result: list[Path] = []
    for path in paths:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise ValueError(f'Choose an existing media file: {path}')
        if path not in result:
            result.append(path)
    return tuple(result)
