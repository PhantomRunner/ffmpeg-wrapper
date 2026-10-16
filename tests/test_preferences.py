"""Preference validation, atomic writes and preservation of incompatible settings."""
import json
from dataclasses import replace

import pytest

from media_wrapper.application.settings_service import SettingsService
from media_wrapper.domain.preferences import Preferences
from media_wrapper.infrastructure.settings_repository import SettingsRepository


@pytest.mark.parametrize('change', [
    {'version': 2}, {'version': True}, {'advanced': 1}, {'page': -1}, {'page': True},
    {'width': 0}, {'height': 90000}, {'container': 'avi'}, {'binary_mode': 'auto'},
    {'binary_directory': '\x00'}, {'recent_destination': 5}, {'unknown': 'keep'},
])
def test_invalid_preferences(change):
    payload = Preferences().to_dict()
    payload.update(change)
    with pytest.raises(ValueError):
        Preferences.from_dict(payload)


def test_roundtrip_defaults_and_unicode(tmp_path):
    path = tmp_path/'config ü'/'settings.json'
    service = SettingsService(SettingsRepository(path))
    assert service.load() == Preferences()
    assert not path.exists()
    expected = replace(Preferences(), binary_mode='bundled', binary_directory='C:/media ü/bin',
                       recent_destination=str(tmp_path/'outputs'), container='mp4', advanced=True, page=5)
    assert service.save(expected) is None
    assert SettingsService(SettingsRepository(path)).load() == expected
    assert json.loads(path.read_text(encoding='utf-8'))['version'] == 1


@pytest.mark.parametrize('text', ['{bad', '{"version": 9}', '[]', 'null', '\ufffd'])
def test_bad_settings_are_preserved(tmp_path, text):
    path = tmp_path/'settings.json'
    path.write_text(text, encoding='utf-8')
    service = SettingsService(SettingsRepository(path))
    assert service.load() == Preferences()
    assert service.warning
    assert service.save(Preferences())
    assert path.read_text(encoding='utf-8') == text


def test_failed_atomic_replace_keeps_previous_file_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path/'settings.json'
    repository = SettingsRepository(path)
    service = SettingsService(repository)
    service.load()
    assert service.save(Preferences()) is None
    before = path.read_bytes()
    def deny(*args):
        raise PermissionError('read only destination')
    monkeypatch.setattr('media_wrapper.infrastructure.settings_repository.os.replace', deny)
    assert service.save(replace(Preferences(), advanced=True))
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_external_change_is_not_overwritten(tmp_path):
    path = tmp_path/'settings.json'
    service = SettingsService(SettingsRepository(path))
    service.load()
    newer = '{"version": 9}'
    path.write_text(newer)
    assert 'outside this session' in service.save(Preferences())
    assert path.read_text() == newer


def test_unwritable_parent_is_actionable(tmp_path):
    blocker = tmp_path/'file'
    blocker.touch()
    service = SettingsService(SettingsRepository(blocker/'settings.json'))
    service.load()
    assert service.save(Preferences())
    assert blocker.is_file()
