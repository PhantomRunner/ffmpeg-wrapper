"""Cancellable recursive local imports; use on a worker, never the Qt event loop."""
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Event


@dataclass(frozen=True)
class ImportResult:
    paths: tuple[Path, ...]
    errors: tuple[str, ...]


def discover_sources(paths: tuple[Path, ...], event: Event) -> ImportResult:
    found, errors = {}, []
    for path in paths:
        if event.is_set():
            break
        try:
            path = path.expanduser().resolve(strict=True)
            if path.is_dir():
                for directory, dirs, files in os.walk(path, followlinks=False,
                                                       onerror=lambda error: errors.append(str(error))):
                    if event.is_set():
                        break
                    dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
                    for name in sorted(files):
                        candidate = Path(directory) / name
                        try:
                            if candidate.is_file():
                                found[candidate.resolve(strict=True)] = None
                        except OSError as error:
                            errors.append(f'{candidate}: {error}')
            elif path.is_file():
                found[path] = None
            else:
                errors.append(f'{path}: not a regular file or directory')
        except (OSError, RuntimeError) as error:
            errors.append(f'{path}: {error}')
    return ImportResult(tuple(found), tuple(errors))
