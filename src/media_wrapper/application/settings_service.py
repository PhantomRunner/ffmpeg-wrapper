"""Preference loading and preservation policy."""
from media_wrapper.application.errors import report_failure
from media_wrapper.domain.preferences import Preferences
from media_wrapper.infrastructure.settings_repository import SettingsRepository


class SettingsService:
    def __init__(self, repository: SettingsRepository, schema=Preferences) -> None:
        self.repository = repository
        self.schema = schema
        self.warning: str | None = None
        self._writable = False
        self._loaded: object = None
        self.loaded_version: int | None = None

    def load(self) -> Preferences:
        self.warning = None
        try:
            self._loaded = self.repository.read()
            self.loaded_version = self._loaded.get('version') if isinstance(self._loaded, dict) else None
            preferences = self.schema() if self._loaded is None else self.schema.from_dict(self._loaded)
            self._writable = True
            return preferences
        except (OSError, ValueError) as error:
            self._writable = False
            self.warning = report_failure('Settings load', error) + (
                ' Using session defaults. The existing file will be preserved; repair it before saving preferences.')
            return self.schema()

    def save(self, preferences: Preferences) -> str | None:
        if not self._writable:
            return self.warning or 'Settings have not been loaded; preferences were not saved.'
        try:
            # Refuse to replace external edits (including newer versions) made during this session.
            if self.repository.read() != self._loaded:
                raise ValueError('Settings changed outside this session; restart to load them before saving')
            payload = self.schema.from_dict(preferences.to_dict()).to_dict()
            self.repository.write(payload)
            self._loaded = payload
            return None
        except (OSError, ValueError) as error:
            return report_failure('Settings save', error) + ' Session preferences were not saved.'
