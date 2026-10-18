from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from PySide6.QtWidgets import QApplication
from test_operation_task import wait

from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_task import OperationTask
from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.media import MediaChapter, MediaFile, MediaStream
from media_wrapper.domain.operation_policy import validate_plan
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    PlanValidationError,
    StreamSelection,
)
from media_wrapper.domain.preferences import Preferences
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
from media_wrapper.infrastructure.ffmpeg.muxers import (
    list_muxers,
    parse_muxers,
    require_muxer,
)
from media_wrapper.ui.output_paths import suggest_output_path


def test_muxer_parser_and_missing_selected_build(monkeypatch):
    assert parse_muxers('Muxers:\n E = Muxing supported\n --\n E matroska Matroska\n E mov,mp4 Alias\n D wav Decode only') == frozenset({'matroska', 'mov', 'mp4'})
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.muxers.list_muxers', lambda *args: frozenset({'mp4'}))
    with pytest.raises(ValueError, match='webm is unavailable'):
        require_muxer(Path('/ffmpeg'), Container.WEBM, Event())


@pytest.mark.parametrize('container,kind,codec', [
    (Container.MOV, 'video', 'mpeg4'), (Container.WEBM, 'video', 'vp8'),
    (Container.WAV, 'audio', 'pcm_s16le'), (Container.FLAC, 'audio', 'flac'),
])
def test_registry_validation_extensions_and_preferences(tmp_path, container, kind, codec):
    spec = CONTAINERS[container]
    media = MediaFile(tmp_path / 'source.mkv', streams=(MediaStream(0, kind, codec),))
    plan = OperationPlan(MediaOperation.REMUX, media, (StreamSelection(0),), OutputTarget(tmp_path / ('out' + spec.extension), container))
    command = CommandBuilder().build(Path('/ffmpeg'), plan)
    assert command[-3:] == ['-f', spec.muxer, str(plan.output.path)]
    assert '-n' in command and command[command.index('-c') + 1] == 'copy'
    assert suggest_output_path(str(tmp_path / 'out.mkv'), container).endswith(spec.extension)
    assert Preferences.from_dict(replace(Preferences(), container=container.value).to_dict()).container == container.value
    with pytest.raises(PlanValidationError, match='must use'):
        validate_plan(replace(plan, output=replace(plan.output, path=tmp_path / 'wrong.xyz')))
    bad = replace(media, streams=(MediaStream(0, 'subtitle', 'dvd_subtitle'),))
    with pytest.raises(PlanValidationError, match='unsupported'):
        validate_plan(replace(plan, media=bad))
    if not spec.chapters:
        with pytest.raises(PlanValidationError, match='Strip chapters'):
            validate_plan(replace(plan, media=replace(media, chapters=(MediaChapter(0, 1),))))
    if spec.max_streams:
        with pytest.raises(PlanValidationError, match='at most'):
            validate_plan(replace(plan, media=replace(media, streams=media.streams + (replace(media.streams[0], index=1),)),
                                  streams=(StreamSelection(0), StreamSelection(1))))


@pytest.mark.parametrize('container,encoder,kind', [
    (Container.MOV, 'mpeg4', 'video'), (Container.WEBM, 'libvpx', 'video'),
    (Container.WAV, 'pcm_s16le', 'audio'), (Container.FLAC, 'flac', 'audio'),
])
def test_real_expanded_remux_verified_publication(sample, tmp_path, container, encoder, kind):
    import subprocess
    binaries, _ = sample
    app = QApplication.instance() or QApplication([])
    assert CONTAINERS[container].muxer in list_muxers(binaries.ffmpeg, Event())
    source = tmp_path / 'generated.mkv'
    signal = 'testsrc2=s=96x64:r=10:d=0.3' if kind == 'video' else 'sine=duration=0.3'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', signal,
                    '-c:v' if kind == 'video' else '-c:a', encoder, '-n', str(source)],
                   check=True, capture_output=True, timeout=15)
    media = MediaService(binaries).inspect(source)
    destination = tmp_path / ('result' + CONTAINERS[container].extension)
    plan = OperationPlan(MediaOperation.REMUX, media, (StreamSelection(0),), OutputTarget(destination, container))
    task = OperationTask(TaskRecord(plan), binaries)
    results = []
    task.finished.connect(lambda *args: results.append(args))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.status == TaskStatus.COMPLETED, task.record.error
    assert destination.exists() and task.record.result.streams[0].codec == media.streams[0].codec
    before = destination.read_bytes()
    repeated = OperationTask(TaskRecord(plan), binaries)
    done = []
    repeated.finished.connect(lambda *args: done.append(args))
    repeated.start()
    wait(app, lambda: bool(done))
    assert repeated.record.status == TaskStatus.FAILED
    assert destination.read_bytes() == before


def test_registry_ui_and_profile_roundtrip(tmp_path):
    from media_wrapper.domain.profile_document import parse_profile, profile_payload
    from media_wrapper.ui.encoding_view import EncodingView
    app = QApplication.instance() or QApplication([])
    view = EncodingView()
    media = MediaFile(tmp_path / 'input.mkv', streams=(MediaStream(0, 'audio', 'flac'),))
    view.set_media(media, False)
    view._encoders[0].setCurrentText('copy')
    for container, spec in CONTAINERS.items():
        view.container.setCurrentIndex(view.container.findData(container.value))
        request = view.request()
        assert request.container is container and request.destination.suffix == spec.extension
        restored = parse_profile(profile_payload(request), request.destination)
        view.apply_request(restored)
        assert view.request() == request
    view.close()
    app.processEvents()
