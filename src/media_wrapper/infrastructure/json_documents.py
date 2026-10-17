"""Bounded strict JSON imports and no-overwrite exports."""
import json
from pathlib import Path
from typing import Any

LIMIT = 1_048_576


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON field: {key}')
        result[key] = value
    return result


def read_document(path: Path) -> Any:
    with path.open('rb') as stream:
        content = stream.read(LIMIT + 1)
    if len(content) > LIMIT:
        raise ValueError('Document exceeds the 1 MiB limit')
    return json.loads(content.decode('utf-8'), object_pairs_hook=_unique)


def write_document(path: Path, payload: Any) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    if len(content) > LIMIT:
        raise ValueError('Document exceeds the 1 MiB limit')
    # Exclusive creation refuses existing files, including symlinks.
    with path.open('xb') as stream:
        stream.write(content)
