"""Atomic, locked local named presets; legacy profile exports remain unchanged."""
from dataclasses import replace
from pathlib import Path

from media_wrapper.domain.named_presets import (
    factory_presets,
    named_presets_document,
    parse_named_preset,
    preset_payload,
)
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

    @staticmethod
    def _document(presets):
        return {'kind': 'media-wrapper-presets', 'version': 2,
                'presets': [preset_payload(preset) for preset in presets.values()]}

    def _write(self, presets):
        payload = self._document(presets)
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
        new = new.strip()
        with document_lock(self.path):
            presets = self._read()
            if old not in presets or new in presets:
                raise ValueError('The old preset is missing or the new name already exists')
            preset = presets.pop(old)
            presets[new] = replace(preset, name=new)
            return self._write(presets)

    def edit(self, old, updated_preset):
        preset = parse_named_preset(preset_payload(updated_preset))
        with document_lock(self.path):
            presets = self._read()
            catalog = factory_presets() | presets
            if old not in presets or (preset.name != old and preset.name in catalog):
                raise ValueError('The old preset is missing or the new name already exists')
            original = presets.pop(old)
            presets[preset.name] = replace(preset, favorite=original.favorite, default=original.default)
            return self._write(presets)

    def duplicate(self, old, new):
        new = new.strip()
        with document_lock(self.path):
            presets = self._read()
            catalog = factory_presets() | presets
            if old not in catalog or new in catalog:
                raise ValueError('The source preset is missing or the new name already exists')
            presets[new] = parse_named_preset(preset_payload(replace(catalog[old], name=new,
                                                                    favorite=False, default=False)))
            return self._write(presets)

    def set_favorite(self, name, favorite):
        with document_lock(self.path):
            presets = self._read()
            preset = (factory_presets() | presets).get(name)
            if preset is None:
                raise ValueError('Choose an existing preset')
            presets[name] = replace(preset, favorite=favorite)
            return self._write(presets)

    def set_default(self, name):
        with document_lock(self.path):
            presets = self._read()
            preset = (factory_presets() | presets).get(name)
            if preset is None:
                raise ValueError('Choose an existing preset')
            if preset.extraction == 'selected':
                raise ValueError('A default preset cannot require selecting specific audio tracks first')
            presets = {key: replace(entry, default=False) if entry.default else entry
                       for key, entry in presets.items()}
            presets[name] = replace(preset, default=True)
            return self._write(presets)

    def reset_factory(self):
        with document_lock(self.path):
            factory = factory_presets()
            return self._write({name: preset for name, preset in self._read().items() if name not in factory})

    def export_presets(self, path, names=()):
        path = Path(path)
        user_presets = self.read()
        catalog = factory_presets() | user_presets
        names = tuple(names)
        if any(name not in catalog for name in names):
            raise ValueError('Choose existing presets to export')
        selection = {name: catalog[name] for name in names} if names else user_presets
        if not selection:
            raise ValueError('Choose at least one preset to export')
        if path.resolve() == self.path.resolve():
            raise ValueError('Choose an export file outside the application preset store')
        SettingsRepository(path).write(self._document(selection))

    def import_presets(self, path, replace_existing=False):
        incoming = named_presets_document(read_document(Path(path)))
        if len([preset for preset in incoming.values() if preset.default]) > 1:
            raise ValueError('The imported catalog must define at most one default preset')
        with document_lock(self.path):
            presets = self._read()
            conflicts = (factory_presets() | presets).keys() & incoming.keys()
            if conflicts and not replace_existing:
                names = ', '.join(sorted(conflicts))
                raise ValueError(f'Confirm replacement of existing presets: {names}')
            if any(preset.default for preset in incoming.values()):
                presets = {key: replace(entry, default=False) if entry.default else entry
                           for key, entry in presets.items()}
            return self._write(presets | incoming)
