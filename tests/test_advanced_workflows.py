"""M8 contract tests and real FFmpeg acceptance coverage."""
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from test_operation_task import wait

from media_wrapper.application.batch_service import output_name, plan_batch
from media_wrapper.application.conversion_service import conversion_plan
from media_wrapper.application.diagnostic_service import (
    diagnostic_snapshot,
    export_diagnostics,
    set_log_level,
)
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_task import OperationTask
from media_wrapper.application.profile_service import export_profile, import_profile
from media_wrapper.application.queue_document_service import load_queue, save_queue
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.custom_options import parse_custom_options
from media_wrapper.domain.media import MediaStream
from media_wrapper.domain.operations import (
    MediaOperation,
    PreservationPolicy,
)
from media_wrapper.domain.profile_document import parse_profile, profile_payload
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
from media_wrapper.infrastructure.json_documents import read_document, write_document
from media_wrapper.ui.encoding_view import EncodingView
from media_wrapper.ui.view_model import DesktopViewModel


def request_for(plan):
    return ConversionRequest(plan.output.path, plan.output.container, ((0, 'copy'),),
                             custom_arguments='-threads 2', metadata_policy=PreservationPolicy.STRIP)


def test_profile_roundtrip_current_build_and_no_overwrite(sample, tmp_path, monkeypatch):
    binaries, plan = sample
    request = request_for(plan)
    path = tmp_path / 'profile.json'
    export_profile(path, request, plan.media, binaries, None)
    assert str(plan.media.path) not in path.read_text()
    assert str(plan.output.path) not in path.read_text()
    assert import_profile(path, plan.output.path, plan.media, binaries, None) == request
    with pytest.raises(FileExistsError):
        export_profile(path, request, plan.media, binaries, None)
    with pytest.raises(ValueError, match='absent'):
        import_profile(path, plan.output.path, replace(plan.media, streams=()), binaries, None)
    encoded = replace(request, tracks=((0, 'aac'),))
    write_document(tmp_path / 'aac.json', profile_payload(encoded))
    monkeypatch.setattr('media_wrapper.application.profile_service.list_encoders', lambda *_: frozenset())
    with pytest.raises(ValueError, match='unavailable'):
        import_profile(tmp_path / 'aac.json', plan.output.path, plan.media, binaries, None)


@pytest.mark.parametrize('key,value', [('audio_bitrate', 128001), ('width', 16386), ('preset', 'bad'),
                                      ('operation', 'remux'), ('custom_arguments', '-y 1'),
                                      ('tracks', [[0, 'h264_nvenc']]), ('track_order', [0, 0]),
                                      ('crf', True), ('metadata_policy', 'guess')])
def test_profile_rejects_unrepresentable_or_unsafe_choices(tmp_path, key, value):
    payload = profile_payload(ConversionRequest(tmp_path / 'out.mkv', Container.MATROSKA, ((0, 'copy'),)))
    payload['settings'][key] = value
    with pytest.raises((ValueError, TypeError)):
        parse_profile(payload, tmp_path / 'out.mkv')


def test_profile_ui_roundtrip_preserves_all_supported_fields(sample):
    app = QApplication.instance() or QApplication([])
    _, plan = sample
    view = EncodingView('Compress')
    view.set_media(plan.media, False)
    request = replace(request_for(plan), operation=MediaOperation.COMPRESS, track_order=(0,), chapter_policy=PreservationPolicy.STRIP)
    view.apply_request(request)
    assert view.request() == request
    view.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('template', ['../{stem}{ext}', '{stem.__class__}{ext}', '{index:04d}{ext}', '{stem!r}{ext}', 'sub\\{stem}{ext}'])
def test_restricted_filename_templates(template):
    with pytest.raises(ValueError):
        output_name(template, Path('a.wav'), 1, '.mkv')


def test_batch_all_or_nothing_and_case_collisions(sample, tmp_path):
    binaries, plan = sample
    second = tmp_path / 'second.wav'
    second.write_bytes(plan.media.path.read_bytes())
    request = request_for(plan)
    plans = plan_batch((plan.media.path, second), request, tmp_path, '{stem}_{index}{ext}', binaries, None)
    assert len(plans) == 2 and not any(p.output.path.exists() for p in plans)
    with pytest.raises(ValueError, match='collision'):
        plan_batch((plan.media.path, second), request, tmp_path, 'constant{ext}', binaries, None)
    with pytest.raises(ValueError, match='collision'):
        plan_batch((second,), request, tmp_path, 'output{ext}', binaries, None, (tmp_path / 'OUTPUT.mkv',))
    (tmp_path / 'second_2.mkv').write_bytes(b'keep')
    with pytest.raises(ValueError, match='exists|collision'):
        plan_batch((plan.media.path, second), request, tmp_path, '{stem}_{index}{ext}', binaries, None)
    assert not (tmp_path / (plan.media.path.stem + '_1.mkv')).exists()
    assert (tmp_path / 'second_2.mkv').read_bytes() == b'keep'


@pytest.mark.parametrize('text', ['-y', '-y 1', '-i input', '-map 0', '-f mp4', '-threads 0', '-threads 65',
                                  '-threads 1 -threads 2', '-threads 2;echo', '-threads ２', '-threads 2 -filter:v scale',
                                  '-max_muxing_queue_size 65537', '-threads $(id)'])
def test_custom_options_cannot_override_safety(text):
    with pytest.raises(ValueError):
        parse_custom_options(text)


def test_custom_options_in_preview_and_direct_plan_validation(sample):
    binaries, plan = sample
    plan = replace(plan, custom_options=parse_custom_options('-threads 2 -max_muxing_queue_size 1024'))
    command = CommandBuilder().build(binaries.ffmpeg, plan)
    assert command[-7:-3] == ['-threads', '2', '-max_muxing_queue_size', '1024']
    assert command.count('-n') == 1 and '-y' not in command
    with pytest.raises(ValueError):
        CommandBuilder().build(binaries.ffmpeg, replace(plan, custom_options=(('-y', '1'),)))


def test_diagnostics_default_omits_private_fields(sample, tmp_path):
    _, plan = sample
    record = TaskRecord(plan, command=('ffmpeg', str(plan.media.path)), log='secret metadata', error='secret error')
    public = diagnostic_snapshot([record])
    text = json.dumps(public)
    assert 'secret' not in text and str(plan.media.path) not in text and str(plan.output.path) not in text
    private = diagnostic_snapshot([record], True)
    assert private['tasks'][0]['log'] == 'secret metadata'
    path = tmp_path / 'diagnostics.json'
    export_diagnostics(path, public)
    with pytest.raises(FileExistsError):
        export_diagnostics(path, private)
    assert read_document(path) == public
    import logging
    logger = logging.getLogger('media_wrapper')
    previous = logger.level
    try:
        set_log_level('WARNING')
        assert logger.level == logging.WARNING
        with pytest.raises(ValueError):
            set_log_level('TRACE')
    finally:
        logger.setLevel(previous)


def test_queue_roundtrip_revalidation_and_new_pending_attempt(sample, tmp_path):
    app = QApplication.instance() or QApplication([])
    binaries, base = sample
    plan = conversion_plan(base.media, request_for(base))
    path = tmp_path / 'queue.json'
    save_queue(path, (plan,))
    assert 'temporary_path' not in path.read_text() and str(binaries.ffmpeg) not in path.read_text()
    assert load_queue(path, binaries) == (plan,)
    model = DesktopViewModel()
    model.state.binaries = binaries
    model.exchange_queue(path, True)
    wait(app, lambda: not model.state.busy)
    assert len(model.queue.records) == 1
    assert model.queue.records[0].status == TaskStatus.PENDING and not model.queue.running
    model.start_queue()
    wait(app, lambda: not model.queue.running)
    assert model.queue.records[0].status == TaskStatus.COMPLETED, model.queue.records[0].error
    with pytest.raises(ValueError, match='exists|collision'):
        load_queue(path, binaries)
    model.deleteLater()
    app.processEvents()


def test_queue_rejects_changed_source_duplicates_and_unknown_schema(sample, tmp_path):
    binaries, plan = sample
    path = tmp_path / 'queue.json'
    save_queue(path, (plan,))
    with pytest.raises(ValueError, match='collision'):
        load_queue(path, binaries, (plan.output.path,))
    with pytest.raises(FileExistsError):
        save_queue(path, (plan,))
    payload = read_document(path)
    payload['jobs'].append(payload['jobs'][0])
    write_document(tmp_path / 'duplicates.json', payload)
    with pytest.raises(ValueError, match='collision'):
        load_queue(tmp_path / 'duplicates.json', binaries)
    payload['jobs'][0]['executable'] = '/bad'
    write_document(tmp_path / 'unsafe.json', payload)
    with pytest.raises(ValueError, match='unknown'):
        load_queue(tmp_path / 'unsafe.json', binaries)
    plan.media.path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        load_queue(path, binaries)
    assert not plan.output.path.exists()


def test_documents_reject_duplicate_fields_unknown_versions_and_oversize(tmp_path):
    path = tmp_path / 'document.json'
    path.write_text('{"version": 1, "version": 2}')
    with pytest.raises(ValueError):
        read_document(path)
    path.write_bytes(b' ' * (1048576 + 1))
    with pytest.raises(ValueError):
        read_document(path)
    from media_wrapper.domain.queue_document import queue_entries
    with pytest.raises(ValueError):
        queue_entries({'kind': 'media-wrapper-queue', 'version': 2, 'jobs': []})


def test_reordered_stream_maps_and_bitmap_subtitle_rejection(sample):
    binaries, base = sample
    media = replace(base.media, streams=(MediaStream(2, 'audio', 'aac'), MediaStream(9, 'subtitle', 'subrip')))
    request = replace(request_for(base), tracks=((2, 'copy'), (9, 'ass')), track_order=(9, 2))
    command = CommandBuilder().build(binaries.ffmpeg, conversion_plan(media, request), frozenset({'ass'}))
    assert command[6:10] == ['-map', '0:9', '-map', '0:2']
    assert command[command.index('-c:0') + 1] == 'ass'
    with pytest.raises(ValueError, match='exactly once'):
        conversion_plan(media, replace(request, track_order=(2,)))
    media = replace(media, streams=(media.streams[0], replace(media.streams[1], codec='hdmv_pgs_subtitle')))
    with pytest.raises(ValueError, match='Bitmap'):
        CommandBuilder().build(binaries.ffmpeg, conversion_plan(media, request), frozenset({'ass'}))


@pytest.mark.parametrize('policy', list(PreservationPolicy))
def test_real_metadata_chapters_and_subtitle_conversion(sample, tmp_path, policy):
    app = QApplication.instance() or QApplication([])
    binaries, base = sample
    metadata = tmp_path / 'metadata.txt'
    metadata.write_text(';FFMETADATA1\ntitle=Private title\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=100\ntitle=Private chapter\n')
    subtitles = tmp_path / 'input.srt'
    subtitles.write_text('1\n00:00:00,000 --> 00:00:00,100\nHello\n')
    source = tmp_path / 'chapters.mkv'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-i', str(base.media.path), '-i', str(subtitles),
                    '-i', str(metadata), '-map', '0:a', '-map', '1:s', '-map_metadata', '2', '-map_chapters', '2',
                    '-metadata:s:a:0', 'language=fra', '-c', 'copy', '-n', str(source)],
                   check=True, capture_output=True, timeout=15)
    media = MediaService(binaries).inspect(source)
    assert len(media.chapters) == 1 and dict(media.tags)['title'] == 'Private title'
    request = replace(request_for(base), tracks=((0, 'copy'), (1, 'ass')), track_order=(1, 0),
                      metadata_policy=policy, chapter_policy=policy)
    task = OperationTask(TaskRecord(conversion_plan(media, request)), binaries)
    results = []
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.status == TaskStatus.COMPLETED, task.record.error + task.record.log
    result = task.record.result
    assert [s.codec for s in result.streams] == ['ass', 'pcm_s16le']
    assert len(result.chapters) == (1 if policy == PreservationPolicy.PRESERVE else 0)
    assert (dict(result.tags).get('title') == 'Private title') == (policy == PreservationPolicy.PRESERVE)
    assert (result.streams[1].language == 'fra') == (policy == PreservationPolicy.PRESERVE)


@pytest.mark.parametrize('container', [Container.MATROSKA, Container.MP4])
def test_real_chapter_preservation_in_supported_containers(sample, tmp_path, container):
    app = QApplication.instance() or QApplication([])
    binaries, base = sample
    metadata = tmp_path / 'chapters.txt'
    metadata.write_text(';FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=100\ntitle=One\n')
    source = tmp_path / 'chapter source.mkv'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-i', str(base.media.path), '-i', str(metadata),
                    '-map', '0:a', '-map_metadata', '1', '-map_chapters', '1', '-c:a', 'aac', '-n', str(source)],
                   check=True, capture_output=True, timeout=15)
    media = MediaService(binaries).inspect(source)
    plan = replace(base, media=media, output=replace(base.output, container=container,
                   path=tmp_path / ('chapters.mp4' if container == Container.MP4 else 'chapters.mkv')))
    task = OperationTask(TaskRecord(plan), binaries)
    finished = []
    task.finished.connect(lambda *r: finished.append(r))
    task.start()
    wait(app, lambda: bool(finished))
    assert task.record.status == TaskStatus.COMPLETED, task.record.error + task.record.log
    assert len(task.record.result.chapters) == 1


@pytest.mark.parametrize('patch', [{'version': True}, {'version': 2}, {'unexpected': 1}])
def test_profile_schema_versions_are_strict(sample, patch):
    _, plan = sample
    payload = profile_payload(request_for(plan))
    payload.update(patch)
    with pytest.raises(ValueError):
        parse_profile(payload, plan.output.path)


@pytest.mark.parametrize('payload', [{'format': {'tags': []}}, {'chapters': {}}, {'chapters': [{'tags': []}]}])
def test_probe_rejects_malformed_new_metadata(payload, tmp_path):
    from media_wrapper.infrastructure.ffmpeg.probe_parser import parse_probe
    with pytest.raises(ValueError):
        parse_probe(tmp_path / 'input', payload)


def test_queue_import_checks_current_encoder_and_missing_source(sample, tmp_path, monkeypatch):
    binaries, base = sample
    plan = conversion_plan(base.media, replace(request_for(base), tracks=((0, 'aac'),)))
    path = tmp_path / 'queue.json'
    save_queue(path, (plan,))
    monkeypatch.setattr('media_wrapper.application.queue_document_service.list_encoders', lambda *_: frozenset())
    with pytest.raises(ValueError, match='unavailable'):
        load_queue(path, binaries)
    base.media.path.unlink()
    with pytest.raises(FileNotFoundError):
        load_queue(path, binaries)


def test_batch_refuses_existing_case_variant_and_windows_name(sample, tmp_path):
    binaries, plan = sample
    (tmp_path / 'OUTPUT.mkv').touch()
    with pytest.raises(ValueError, match='collision'):
        plan_batch((plan.media.path,), request_for(plan), tmp_path, 'output{ext}', binaries, None)
    with pytest.raises(ValueError, match='reserved'):
        plan_batch((plan.media.path,), request_for(plan), tmp_path, 'CON{ext}', binaries, None)


def test_busy_model_prevents_document_overlap(sample, tmp_path):
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    model = DesktopViewModel()
    model.state.binaries, model.state.media, model.state.busy = binaries, plan.media, True
    path = tmp_path / 'ignored.json'
    model.exchange_queue(path, False)
    model.exchange_profile(path, request_for(plan), False)
    model.export_diagnostics(path, False)
    model.enqueue_batch((plan.media.path,), request_for(plan), tmp_path, '{stem}{ext}')
    assert model.thread is None and not path.exists() and model.queue.records == []
    model.deleteLater()
    app.processEvents()
