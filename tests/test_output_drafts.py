from dataclasses import replace
from threading import Event

import pytest

from media_wrapper.application.draft_service import prepare_draft, snapshot_draft
from media_wrapper.application.import_service import discover_sources
from media_wrapper.application.operation_validation import validate_paths
from media_wrapper.domain.draft import MIXED, DraftState, EditScope
from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
from media_wrapper.domain.named_presets import capture_preset
from media_wrapper.domain.operations import EncodingProfile, MediaOperation, StreamSelection
from media_wrapper.domain.queue_document import parse_definition, plan_payload


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


def test_typed_size_limit_replaces_legacy_cap_and_prepares_real_plan(video_sample):
    binaries, plan = video_sample
    draft = DraftState(multiple_outputs=True)
    item, = draft.add((plan.media.path,))
    draft.inspected(InspectionRecord(item.path, InspectionStatus.COMPLETED, plan.media))
    draft.set_operation(MediaOperation.COMPRESS)
    draft.patch('mode', 'target')
    assert draft.value('target_size_bytes') == 104857600
    draft.patch('target_size', ('0.2', 'MB'))
    assert draft.value('target_size_bytes') is None
    result, = prepare_draft(snapshot_draft(draft), binaries).ready
    assert result.plan.target_size_bytes == 200000 and result.plan.two_pass


def test_prepared_destination_cannot_be_replaced_before_execution(sample, tmp_path):
    binaries, plan = sample
    draft = DraftState(multiple_outputs=True)
    source, = draft.add((plan.media.path,))
    draft.inspected(InspectionRecord(source.path, InspectionStatus.COMPLETED, plan.media))
    destination = tmp_path / 'drive'
    destination.mkdir()
    draft.patch('folder', str(destination))
    prepared, = prepare_draft(snapshot_draft(draft), binaries).ready
    saved = plan_payload(prepared.plan, prepared.fingerprint)
    restored = parse_definition(saved, prepared.plan.media)
    destination.rename(tmp_path / 'disconnected-drive')
    destination.mkdir()
    with pytest.raises(ValueError, match='Destination directory changed'):
        validate_paths(restored)
    assert not tuple(destination.iterdir())


def test_hardware_result_reuse_preserves_policy_and_can_be_saved_as_a_preset(video_sample):
    _, plan = video_sample
    hardware_plan = replace(plan, operation=MediaOperation.CONVERT, cpu_fallback=True,
                            streams=(StreamSelection(0, EncodingProfile('h264_nvenc', bitrate=900000)),
                                     StreamSelection(1)))
    draft = DraftState(multiple_outputs=True)
    output = draft.reuse_plan(hardware_plan)
    request = output.options[output.operation].request
    assert request.hardware_mode == 'Prefer GPU' and request.gpu_encoder == 'h264_nvenc'
    assert request.tracks == ((0, 'libx264'), (1, 'copy'))
    saved = capture_preset(draft, 'Hardware preference')
    assert saved.track_rules[0].profile.bitrate == 900000
    assert hardware_plan.streams[0].profile.encoder == 'h264_nvenc'
