"""UTF-8 settings storage with atomic replacement and no temporary-file leaks."""
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class SettingsRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> Any:
        try:
            with self.path.open('r', encoding='utf-8') as stream:
                text = stream.read(262145)
        except FileNotFoundError:
            return None
        if len(text) > 262144:
            raise ValueError('Settings file is too large')
        payload = json.loads(text)
        if payload is None:
            raise ValueError('Settings document cannot be null')
        return payload

    def write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.settings-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
