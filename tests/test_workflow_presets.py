import json
import subprocess
from dataclasses import replace
from hashlib import sha256

import pytest
from test_overhaul_processing import run_task

from media_wrapper.application.draft_service import prepare_draft, snapshot_draft
from media_wrapper.application.media_service import MediaService
from media_wrapper.domain.draft import DraftState
from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
from media_wrapper.domain.named_presets import (
    apply_named_preset,
    capture_preset,
    factory_presets,
    preset_payload,
)
from media_wrapper.domain.operations import EncodingProfile, MediaOperation
from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.infrastructure.preset_repository import PresetRepository


@pytest.fixture
def obs_clip(sample, tmp_path):
    binaries, _ = sample
    path = tmp_path / 'OBS — Match.mkv'
    subprocess.run(
        [str(binaries.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=30:d=1',
         '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
         '-f', 'lavfi', '-i', 'sine=frequency=880:duration=1', '-map', '0:v', '-map', '1:a',
         '-map', '2:a', '-c:v', 'libaom-av1', '-strict:v', 'experimental', '-cpu-used', '8',
         '-threads', '2', '-c:a', 'aac',
         '-metadata:s:a:0', 'title=Game', '-metadata:s:a:1', 'title=Microphone', '-n', str(path)],
        check=True, capture_output=True, timeout=30,
    )
    return binaries, MediaService(binaries).inspect(path)


def drafts_for(*sources):
    draft = DraftState(multiple_outputs=True)
    items = draft.add(tuple(source.path for source in sources))
    for source in sources:
        draft.inspected(InspectionRecord(source.path, InspectionStatus.COMPLETED, source))
    return draft, items


def test_catalog_edits_and_extraction_prepare_independent_obs_outputs(obs_clip):
    binaries, source = obs_clip
    reference = sha256(source.path.read_bytes()).digest()
    draft, (item,) = drafts_for(source)
    catalog = factory_presets()
    edit = apply_named_preset(draft, catalog['DaVinci Resolve — Linux'])[0]
    extraction_target = draft.add_output(item.id)
    extraction, microphone = apply_named_preset(draft, catalog['Extract All Audio'], (extraction_target.id,))
    assert [output.label for output in (extraction, microphone)] == ['Game', 'Microphone']
    assert draft.active_output_id == edit.id

    results = prepare_draft(snapshot_draft(draft), binaries)
    assert len(results.ready) == 3, [entry.validation.error for entry in results.items]
    editor_plan, game_plan, mic_plan = [entry.plan for entry in results.ready]
    assert [stream.profile.encoder for stream in editor_plan.streams] == ['dnxhd', 'pcm_s24le', 'pcm_s24le']
    assert game_plan.output.path.name.endswith('_audio_1_Game.wav')
    assert mic_plan.output.path.name.endswith('_audio_2_Microphone.wav')
    assert [stream.index for stream in game_plan.streams] == [1]
    assert [stream.index for stream in mic_plan.streams] == [2]
    for extracted in (game_plan, mic_plan):
        outcome = run_task(extracted, binaries)
        assert outcome.status is TaskStatus.COMPLETED, outcome.error
        assert [(stream.kind, stream.codec) for stream in outcome.result.streams] == [('audio', 'pcm_s24le')]
    assert sha256(game_plan.output.path.read_bytes()).digest() != sha256(mic_plan.output.path.read_bytes()).digest()
    copied = apply_named_preset(draft, catalog['Extract All Audio — Copy'], (extraction.id,))
    assert all(output.options[output.operation].request.container.value == 'm4a' for output in copied)
    assert all('copy' in dict(output.options[output.operation].request.tracks).values() for output in copied)
    assert sha256(source.path.read_bytes()).digest() == reference


def test_portable_preset_retains_named_track_rules_and_independent_settings(obs_clip, tmp_path):
    _, source = obs_clip
    second = replace(source, path=tmp_path / 'other.mkv',
                     streams=tuple(replace(stream, index=stream.index + 20) for stream in source.streams))
    draft, (first, other) = drafts_for(source, second)
    draft.set_operation(MediaOperation.CONVERT)
    draft.patch('tracks', ((0, 'copy'), (1, 'omit'), (2, 'aac')))
    draft.patch('stream_profiles', ((2, EncodingProfile('aac', bitrate=96000, sample_rate=48000)),))
    saved = capture_preset(draft, 'Voiceover', 'Review')
    store = PresetRepository(tmp_path / 'presets.json')
    store.save(saved)
    store.set_favorite('Voiceover', True)
    store.set_default('Voiceover')
    exported = tmp_path / 'portable.json'
    store.export_presets(exported, ('Voiceover',))
    assert str(source.path) not in exported.read_text(encoding='utf-8')
    target_store = PresetRepository(tmp_path / 'portable-store.json')
    loaded = target_store.import_presets(exported)['Voiceover']
    assert loaded.favorite and loaded.default and loaded.category == 'Review'
    assert target_store.duplicate('Voiceover', 'Copy')['Copy'].default is False

    target, = draft.outputs_for(other.id)
    apply_named_preset(draft, loaded, (target.id,))
    request = target.options[target.operation].request
    assert request.tracks == ((20, 'copy'), (21, 'omit'), (22, 'aac'))
    assert dict(request.stream_profiles)[22].sample_rate == 48000
    draft.patch('audio_bitrate', 64000, (target.id,))
    assert dict(loaded.settings)['audio_bitrate'] != 64000
    assert first.id != other.id


def test_version_one_catalog_can_be_read_and_factory_reset_preserves_user_entry(tmp_path):
    from media_wrapper.domain.named_presets import named_presets_document
    factory = factory_presets()
    entry = preset_payload(factory['Lossless Remux'])
    entry = {key: entry[key] for key in ('name', 'operation', 'settings', 'streams')}
    entry['name'] = 'My remux'
    entry['settings'].pop('deep_verify', None)
    legacy = {'kind': 'media-wrapper-presets', 'version': 1, 'presets': [entry]}
    path = tmp_path / 'old.json'
    path.write_text(json.dumps(legacy), encoding='utf-8')
    store = PresetRepository(path)
    assert set(named_presets_document(legacy)) == {'My remux'}
    assert set(store.set_favorite('Lossless Remux', True)) == {'My remux', 'Lossless Remux'}
    assert set(store.reset_factory()) == {'My remux'}


def test_generated_full_duration_match_review_keeps_selected_audio(sample, tmp_path):
    binaries, _ = sample
    path = tmp_path / 'Long match.mkv'
    subprocess.run(
        [str(binaries.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=160x96:r=15:d=75',
         '-f', 'lavfi', '-i', 'sine=frequency=440:duration=75:sample_rate=16000',
         '-f', 'lavfi', '-i', 'sine=frequency=880:duration=75:sample_rate=16000',
         '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:v', 'libx264', '-preset', 'ultrafast',
         '-threads', '2', '-c:a', 'aac', '-metadata:s:a:0', 'title=Game',
         '-metadata:s:a:1', 'title=Microphone', '-n', str(path)],
        check=True, capture_output=True, timeout=30,
    )
    media = MediaService(binaries).inspect(path)
    source_hash = sha256(path.read_bytes()).digest()
    draft, _ = drafts_for(media)
    apply_named_preset(draft, factory_presets()['Match Review'])
    draft.patch('height', None)
    draft.patch('video_encoder', 'libx264')
    draft.patch('preset', 'ultrafast')
    draft.patch('tracks', ((0, 'libx264'), (1, 'copy'), (2, 'omit')))
    draft.patch('deep_verify', True)
    prepared, = prepare_draft(snapshot_draft(draft), binaries).ready
    result = run_task(prepared.plan, binaries)
    assert result.status is TaskStatus.COMPLETED, result.error
    assert abs(result.result.duration - media.duration) < 0.25
    assert [(stream.kind, stream.title) for stream in result.result.streams] == [('video', None), ('audio', 'Game')]
    assert result.result.streams[0].frame_rate == media.streams[0].frame_rate
    assert sha256(path.read_bytes()).digest() == source_hash
