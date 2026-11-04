"""Atomic, locked local named presets; legacy profile exports remain unchanged."""
from dataclasses import replace

from media_wrapper.domain.named_presets import named_presets_document, preset_payload
from media_wrapper.infrastructure.document_lock import document_lock
from media_wrapper.infrastructure.json_documents import read_document
from media_wrapper.infrastructure.settings_repository import SettingsRepository


class PresetRepository:
    def __init__(self, path):
        self.path = path

    def _read(self):
        return named_presets_document(read_document(self.path)) if self.path.exists() else {}

    def read(self):
        if not self.path.exists():
            return {}
        with document_lock(self.path):
            return self._read()

    def _write(self, presets):
        payload = {'kind': 'media-wrapper-presets', 'version': 1,
                   'presets': [preset_payload(preset) for preset in presets.values()]}
        named_presets_document(payload)
        SettingsRepository(self.path).write(payload)
        return presets

    def save(self, preset, replace_existing=False):
        with document_lock(self.path):
            presets = self._read()
            if preset.name in presets and not replace_existing:
                raise ValueError('A preset with this name already exists')
            presets[preset.name] = preset
            return self._write(presets)

    def delete(self, names):
        with document_lock(self.path):
            presets = self._read()
            for name in names:
                presets.pop(name, None)
            return self._write(presets)

    def rename(self, old, new):
        with document_lock(self.path):
            presets = self._read()
            if old not in presets or new in presets:
                raise ValueError('The old preset is missing or the new name already exists')
            preset = presets.pop(old)
            presets[new] = replace(preset, name=new)
            return self._write(presets)
