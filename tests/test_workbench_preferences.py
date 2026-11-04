from dataclasses import replace

import pytest

from media_wrapper.application.settings_service import SettingsService
from media_wrapper.domain.preferences import Preferences
from media_wrapper.domain.workbench_preferences import WorkbenchPreferences
from media_wrapper.infrastructure.settings_repository import SettingsRepository


@pytest.mark.parametrize('page,route,operation', [(0, 'workspace', 'remux'), (1, 'workspace', 'remux'),
                                               (2, 'workspace', 'convert'), (3, 'workspace', 'compress'),
                                               (4, 'queue', 'remux'), (5, 'settings', 'remux')])
def test_legacy_settings_migrate_without_losing_supported_choices(page, route, operation):
    legacy = Preferences(page=page, binary_directory='/custom/ffmpeg', recent_destination='/output', log_level='DEBUG')
    prefs = WorkbenchPreferences.from_dict(legacy.to_dict())
    assert prefs.version == 2 and (prefs.route, prefs.operation) == (route, operation)
    assert prefs.binary_directory == legacy.binary_directory and prefs.recent_destination == legacy.recent_destination


def test_preferences_roundtrip_unknown_versions_and_external_edits(tmp_path):
    path = tmp_path / 'settings.json'
    repository = SettingsRepository(path)
    service = SettingsService(repository, WorkbenchPreferences)
    preferences = replace(service.load(), naming_template='{stem}_{operation}_{index}', auto_number=True,
                          output_folder=str(tmp_path), route='queue', gpu_device='/dev/dri/renderD128')
    assert service.save(preferences) is None
    assert service.load() == preferences
    original = path.read_bytes()
    repository.write({'version': 99})
    service.load()
    assert service.save(preferences) and path.read_text().strip() == '{\n  "version": 99\n}'
    path.write_bytes(original)
    service.load()
    path.write_text('{}')
    assert service.save(preferences) and path.read_text() == '{}'
