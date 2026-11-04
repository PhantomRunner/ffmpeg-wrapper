from dataclasses import replace

import pytest
from test_draft import draft_pair

from media_wrapper.domain.draft import MIXED, EditScope
from media_wrapper.domain.named_presets import apply_named_preset, capture_preset
from media_wrapper.domain.operations import MediaOperation
from media_wrapper.infrastructure.preset_repository import PresetRepository


def test_named_preset_maps_semantic_streams_without_copying_indices(tmp_path):
    draft, (a, b) = draft_pair(tmp_path)
    draft.operation = MediaOperation.COMPRESS
    draft.scope, draft.selected = EditScope.SELECTED, (a.id,)
    draft.patch('crf', 31)
    preset = capture_preset(draft, 'Small H264')
    repository = PresetRepository(tmp_path / 'presets.json')
    repository.save(preset)
    stored = repository.read()['Small H264']
    assert stored == preset and 'tracks' not in repository.path.read_text()
    draft.selected = (b.id,)
    apply_named_preset(draft, stored)
    assert b.options[draft.operation].request.tracks == ((3, 'libx264'),)
    assert b.options[draft.operation].request.crf == 31
    draft.patch('crf', 25)
    assert b.options[draft.operation].preset_name == 'Small H264'
    assert b.options[draft.operation].preset_modified
    assert a.options[draft.operation].request.crf == 31
    draft.scope = EditScope.INCLUDED
    assert draft.value('crf') is MIXED
    with pytest.raises(ValueError, match='mixed'):
        capture_preset(draft, 'Mixed')


def test_store_preserves_unknown_files_and_handles_names(tmp_path):
    draft, _ = draft_pair(tmp_path)
    preset = capture_preset(draft, 'Remux MKV')
    repository = PresetRepository(tmp_path / 'presets.json')
    repository.save(preset)
    assert repository.read()['Remux MKV'].operation == MediaOperation.REMUX
    with pytest.raises(ValueError, match='already exists'):
        repository.save(preset)
    repository.rename('Remux MKV', 'Archive')
    assert set(repository.read()) == {'Archive'}
    with pytest.raises(ValueError):
        repository.rename('Archive', '')
    repository.delete(('Archive',))
    assert not repository.read()
    repository.path.write_text('{"kind":"media-wrapper-presets","version":99,"presets":[]}')
    original = repository.path.read_bytes()
    with pytest.raises(ValueError):
        repository.save(replace(preset, name='Other'))
    assert repository.path.read_bytes() == original
