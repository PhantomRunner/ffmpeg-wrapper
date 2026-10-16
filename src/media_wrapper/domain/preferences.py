"""Versioned, Qt-independent desktop preference schema."""
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Preferences:
    version: int = 1
    binary_mode: str = 'external'
    binary_directory: str = ''
    recent_destination: str | None = None
    container: str = 'matroska'
    advanced: bool = False
    page: int = 0
    width: int = 900
    height: int = 650

    @classmethod
    def from_dict(cls, payload: Any) -> 'Preferences':
        if not isinstance(payload, dict):
            raise ValueError('Settings must be a JSON object')  # noqa: TRY004 - invalid serialized value
        if type(payload.get('version')) is not int or payload['version'] != 1:
            raise ValueError('Unsupported settings version; this application supports version 1')
        values = asdict(cls())
        if set(payload) - set(values):
            raise ValueError('Settings contain unknown fields; preserve them for a compatible application')
        values.update(payload)
        if values['binary_mode'] not in ('external', 'bundled'):
            raise ValueError('Invalid binary mode')
        if values['container'] not in ('matroska', 'mp4'):
            raise ValueError('Invalid output container')
        for key in ('binary_directory', 'recent_destination'):
            value = values[key]
            if key == 'recent_destination' and value is None:
                continue
            if not isinstance(value, str) or '\x00' in value or len(value) > 32768:
                raise ValueError(f'Invalid {key}')
        if type(values['advanced']) is not bool:
            raise ValueError('Invalid advanced preference')
        for key, low, high in (('page', 0, 5), ('width', 640, 8192), ('height', 480, 8192)):
            value = values[key]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'Invalid {key}')
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
