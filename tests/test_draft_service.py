from dataclasses import replace

from media_wrapper.application.draft_service import (
    draft_output_name,
    prepare_draft,
    snapshot_draft,
)
from media_wrapper.domain.draft import DraftState
from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
from media_wrapper.domain.operations import MediaOperation


def prepared_sources(sample, tmp_path):
    binaries, plan = sample
    draft = DraftState()
    second = tmp_path / 'second.wav'
    second.write_bytes(plan.media.path.read_bytes())
    items = draft.add((plan.media.path, second, tmp_path / 'missing.wav'))
    for item in items[:2]:
        draft.inspected(InspectionRecord(item.path, InspectionStatus.COMPLETED,
                                         replace(plan.media, path=item.path)))
    return binaries, draft, items


def test_prepare_ready_subset_real_commands_and_frozen_settings(sample, tmp_path):
    binaries, draft, items = prepared_sources(sample, tmp_path)
    snapshot = snapshot_draft(draft)
    result = prepare_draft(snapshot, binaries)
    assert len(result.ready) == 2 and len(result.items) == 3
    assert result.items[2].validation.field == 'input'
    for item in result.ready:
        assert item.plan.operation == MediaOperation.REMUX
        command = item.validation.commands[0]
        assert command[command.index('-c') + 1] == 'copy'
        assert '-n' in command and '-y' not in command
        assert not item.plan.output.path.exists()
    draft.patch('template', '{name}_different')
    assert snapshot.inputs[0].options.template == '{name}_{operation}'
    assert result.ready[0].plan.output.path.name.endswith('_remux.mkv')
    assert items[0].path.exists()


def test_duplicate_destinations_block_both_and_auto_number_reserves_sources(sample, tmp_path):
    binaries, draft, _ = prepared_sources(sample, tmp_path)
    draft.patch('template', 'same')
    result = prepare_draft(snapshot_draft(draft), binaries)
    assert not result.ready
    assert all(item.validation.field == 'output' for item in result.items[:2])
    (tmp_path / 'SAME.mkv').write_bytes(b'keep')
    draft.patch('auto_number', True)
    result = prepare_draft(snapshot_draft(draft), binaries, reserved=(tmp_path / 'same_1.mkv',))
    assert [item.plan.output.path.name for item in result.ready] == ['same_2.mkv', 'same_3.mkv']
    assert (tmp_path / 'SAME.mkv').read_bytes() == b'keep'


def test_template_aliases_and_no_path_or_format_expressions(tmp_path):
    import pytest
    source = tmp_path / 'clip.v1.mkv'
    assert draft_output_name('{name}_{operation}', source, MediaOperation.COMPRESS, 1, '.mp4') == 'clip.v1_compress.mp4'
    assert draft_output_name('{stem}_{index}{ext}', source, MediaOperation.REMUX, 2, '.mkv') == 'clip.v1_2.mkv'
    for template in ('../{name}', '{name.__class__}', '{index:04}', '{name!r}', '{ext}_tail'):
        with pytest.raises(ValueError):
            draft_output_name(template, source, MediaOperation.REMUX, 1, '.mkv')
