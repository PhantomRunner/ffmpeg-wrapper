import subprocess
from dataclasses import replace
from fractions import Fraction
from threading import Event

import pytest
from PySide6.QtWidgets import QApplication
from test_operation_task import wait

from media_wrapper.application.conversion_service import (
    ConversionRequest,
    conversion_plan,
)
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_task import OperationTask
from media_wrapper.domain.operations import (
    EncodingProfile,
    PlanValidationError,
    StreamSelection,
)
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders, parse_encoders
from media_wrapper.ui.encoding_view import EncodingView


def test_encoder_list_parser():
    assert parse_encoders(' V..... = Video\n V....D libx264 H.264\n A..... aac AAC\n S..... mov_text Text') == frozenset({'libx264', 'aac', 'mov_text'})


@pytest.fixture
def video_sample(sample, tmp_path):
    binaries, plan = sample
    source = tmp_path/'video ü.mkv'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=96x64:r=24:d=0.5',
                    '-i', str(plan.media.path), '-c:v', 'ffv1', '-c:a', 'copy', '-n', str(source)],
                   check=True, capture_output=True, timeout=15)
    return binaries, replace(plan, media=MediaService(binaries).inspect(source))


def test_real_conversion_scales_and_verifies(video_sample):
    app = QApplication.instance() or QApplication([])
    binaries, base = video_sample
    if 'libx264' not in list_encoders(binaries.ffmpeg, Event()):
        pytest.skip('Selected FFmpeg lacks libx264')
    plan = conversion_plan(base.media, ConversionRequest(base.output.path, base.output.container,
                           ((0, 'libx264'), (1, 'aac')), 64, 48, '12'))
    task = OperationTask(TaskRecord(plan), binaries)
    results = []
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.status == TaskStatus.COMPLETED, task.record.error
    video, audio = task.record.result.streams
    assert (video.codec, video.width, video.height, video.frame_rate) == ('h264', 64, 48, Fraction(12))
    assert audio.codec == 'aac'


@pytest.mark.parametrize('profile', [EncodingProfile('copy', width=64, height=48),
                                     EncodingProfile('libx264', width=63, height=48),
                                     EncodingProfile('libx264', fps=Fraction(-1))])
def test_invalid_video_options(video_sample, profile):
    _, base = video_sample
    plan = conversion_plan(base.media, ConversionRequest(base.output.path, base.output.container, ((0, 'libx264'),)))
    with pytest.raises(PlanValidationError):
        CommandBuilder().build(base.media.path, replace(plan, streams=(StreamSelection(0, profile),)), frozenset({'libx264'}))


def test_convert_form_explicit_track_choices(sample):
    app = QApplication.instance() or QApplication([])
    _, base = sample
    view = EncodingView()
    view.set_media(base.media, False)
    assert view.request().tracks == ((0, 'aac'),)
    view._encoders[0].setCurrentText('copy')
    assert view.request().tracks == ((0, 'copy'),)
    view.set_media(base.media, True)
    assert not view.run_button.isEnabled()
    view.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('encoder', ['libx264', 'libx265'])
def test_quality_and_preset_options(video_sample, encoder):
    _, base = video_sample
    request = ConversionRequest(base.output.path, base.output.container, ((0, encoder), (1, 'aac')),
                                mode='quality', crf=28, preset='slow', audio_quality=3)
    plan = conversion_plan(base.media, request)
    command = CommandBuilder().build(base.media.path, plan, frozenset({encoder, 'aac'}))
    assert command[command.index('-crf:0') + 1] == '28'
    assert command[command.index('-preset:0') + 1] == 'slow'
    assert command[command.index('-q:1') + 1] == '3'
    assert '-b:0' not in command and '-b:1' not in command


@pytest.mark.parametrize('profile', [EncodingProfile('libx264', bitrate=100000, crf=23),
                                     EncodingProfile('ffv1', crf=23), EncodingProfile('libx265', preset='invalid'),
                                     EncodingProfile('libx264', crf=52)])
def test_conflicting_quality_options(video_sample, profile):
    _, base = video_sample
    plan = conversion_plan(base.media, ConversionRequest(base.output.path, base.output.container, ((0, 'libx264'),)))
    with pytest.raises(PlanValidationError):
        CommandBuilder().build(base.media.path, replace(plan, streams=(StreamSelection(0, profile),)), frozenset({'libx264', 'libx265', 'ffv1'}))
