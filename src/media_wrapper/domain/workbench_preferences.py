"""Version-2 workbench preferences, with lossless reads of version-1 choices."""
from dataclasses import asdict, dataclass

from media_wrapper.domain.operations import MediaOperation
from media_wrapper.domain.output_naming import draft_output_name
from media_wrapper.domain.preferences import Preferences


@dataclass(frozen=True)
class WorkbenchPreferences(Preferences):
    version: int = 2
    width: int = 1280
    height: int = 800
    page: int = 1
    route: str = 'workspace'
    operation: str = 'remux'
    output_folder: str = ''
    naming_template: str = '{name}_{operation}'
    auto_number: bool = False
    remember_window: bool = True
    gpu_device: str = ''

    @classmethod
    def from_dict(cls, payload):
        from pathlib import Path
        if not isinstance(payload, dict):
            raise ValueError('Settings must be a JSON object')  # noqa: TRY004 - serialized data
        if type(payload.get('version')) is not int:
            raise ValueError('Invalid settings version')
        if payload['version'] == 1:
            legacy = Preferences.from_dict(payload)
            route = 'queue' if legacy.page == 4 else 'settings' if legacy.page == 5 else 'workspace'
            operation = {2: 'convert', 3: 'compress'}.get(legacy.page, 'remux')
            values = legacy.to_dict()
            values.update(version=2, route=route, operation=operation)
            return cls(**values)
        if payload['version'] != 2 or set(payload) - set(asdict(cls())):
            raise ValueError('Unsupported settings version or unknown fields; preserve the original document')
        values = asdict(cls())
        values.update(payload)
        legacy_keys = set(asdict(Preferences()))
        Preferences.from_dict({key: 1 if key == 'version' else values[key] for key in legacy_keys})
        if values['route'] not in ('workspace', 'queue', 'settings'):
            raise ValueError('Invalid page route')
        operation = MediaOperation(values['operation'])
        for key in ('output_folder', 'gpu_device', 'naming_template'):
            if not isinstance(values[key], str) or '\x00' in values[key] or len(values[key]) > (256 if key == 'naming_template' else 32768):
                raise ValueError(f'Invalid {key}')
        for key in ('auto_number', 'remember_window'):
            if type(values[key]) is not bool:
                raise ValueError(f'Invalid {key}')
        draft_output_name(values['naming_template'], Path('source.mkv'), operation, 1, '.mkv')
        return cls(**values)
