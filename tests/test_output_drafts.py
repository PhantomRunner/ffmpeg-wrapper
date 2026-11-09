from threading import Event

from media_wrapper.application.draft_service import prepare_draft, snapshot_draft
from media_wrapper.application.import_service import discover_sources
from media_wrapper.domain.draft import MIXED, DraftState, EditScope
from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
from media_wrapper.domain.operations import MediaOperation


def test_multiple_outputs_have_independent_scope_inclusion_and_snapshots(sample):
    binaries, plan = sample
    draft = DraftState(multiple_outputs=True)
    source, = draft.add((plan.media.path,))
    draft.inspected(InspectionRecord(source.path, InspectionStatus.COMPLETED, plan.media))
    primary, = draft.outputs_for(source.id)
    extra = draft.add_output(source.id, 'Archive', MediaOperation.CONVERT)
    assert primary.source_id == extra.source_id == source.id
    assert draft.active_output_id == primary.id
    draft.inspector_source_id = source.id
    draft.focus_output(extra.id)
    assert draft.inspector_source_id == source.id
    draft.patch('audio_bitrate', 192000)
    before = extra.options[extra.operation].request

    draft.scope = EditScope.SELECTED
    draft.selected_outputs = (primary.id, extra.id)
    assert draft.value('audio_bitrate') is MIXED
    draft.patch('auto_number', True)
    assert extra.options[extra.operation].request == before

    draft.include_output(primary.id, False)
    assert source.included and extra.included
    snapshot = snapshot_draft(draft)
    assert [item.id for item in snapshot.inputs] == [extra.id]
    draft.include(source.id, True)
    full = snapshot_draft(draft)
    assert [item.id for item in full.inputs] == [primary.id, extra.id]
    assert [item.operation for item in full.inputs] == [MediaOperation.REMUX, MediaOperation.CONVERT]
    result = prepare_draft(full, binaries)
    assert len(result.ready) == 2
    assert len({item.plan.output.path for item in result.ready}) == 2
    assert len({id(item.plan.media) for item in result.ready}) == 1
    draft.patch('audio_bitrate', 64000)
    assert snapshot.inputs[0].options.request == before


def test_directory_preserves_explicit_recursion_choice(tmp_path):
    nested = tmp_path / 'nested'
    nested.mkdir()
    (tmp_path / 'top.wav').touch()
    (nested / 'deep.wav').touch()
    immediate = discover_sources((tmp_path,), Event(), recursive=False)
    assert immediate.paths == (tmp_path / 'top.wav',)
    recursive = discover_sources((tmp_path,), Event(), recursive=True)
    assert set(recursive.paths) == {tmp_path / 'top.wav', nested / 'deep.wav'}
