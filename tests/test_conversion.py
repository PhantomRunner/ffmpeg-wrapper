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


def test_target_size_estimate_and_two_pass(video_sample):
    from media_wrapper.domain.target_size import apply_target_size
    _, base = video_sample
    request = ConversionRequest(base.output.path, base.output.container, ((0, 'libx264'), (1, 'aac')),
                                mode='target', target_size_bytes=100000)
    plan = apply_target_size(conversion_plan(base.media, request))
    assert plan.two_pass and plan.streams[0].profile.crf is None
    assert plan.streams[0].profile.bitrate == int(100000 * 8 * .98 / base.media.duration - 128000)
    commands = CommandBuilder().build_passes(base.media.path, plan, frozenset({'libx264', 'aac'}), base.output.path.with_suffix('.log'))
    assert len(commands) == 2
    assert commands[0][commands[0].index('-pass:0') + 1] == '1'
    assert commands[1][commands[1].index('-pass:0') + 1] == '2'


def test_real_two_pass_compression(video_sample):
    app = QApplication.instance() or QApplication([])
    binaries, base = video_sample
    if 'libx264' not in list_encoders(binaries.ffmpeg, Event()):
        pytest.skip('No libx264')
    request = ConversionRequest(base.output.path, base.output.container, ((0, 'libx264'), (1, 'aac')),
                                mode='target', target_size_bytes=100000, preset='ultrafast')
    task = OperationTask(TaskRecord(conversion_plan(base.media, request)), binaries)
    results = []
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.status == TaskStatus.COMPLETED, task.record.error + task.record.log
    assert task.record.result.streams[0].codec == 'h264'
    assert task._pass_directory is None


@pytest.mark.parametrize('change', ['duration', 'audio', 'encoder', 'tiny'])
def test_target_size_invalid_inputs(video_sample, change):
    from media_wrapper.domain.target_size import apply_target_size
    _, base = video_sample
    request = ConversionRequest(base.output.path, base.output.container, ((0, 'libx264'), (1, 'aac')),
                                mode='target', target_size_bytes=100000)
    if change == 'duration':
        base = replace(base, media=replace(base.media, duration=None))
    elif change == 'audio':
        request = replace(request, audio_quality=3)
    elif change == 'encoder':
        request = replace(request, tracks=((0, 'libx265'),))
    else:
        request = replace(request, target_size_bytes=1)
    with pytest.raises(PlanValidationError):
        apply_target_size(conversion_plan(base.media, request))


def test_presets_are_editable_and_audio_only_is_explicit(video_sample):
    app = QApplication.instance() or QApplication([])
    _, plan = video_sample
    view = EncodingView('Compress')
    view.set_media(plan.media, False)
    view.apply_preset()
    assert view.request().tracks == ((0, 'libx264'), (1, 'aac'))
    assert view.request().crf == 20
    view.crf.setValue(25)
    assert view.request().crf == 25
    view.presets.setCurrentIndex(1)
    view.apply_preset()
    assert view.request().tracks[0][1] == 'libx265'
    view.presets.setCurrentIndex(2)
    view.apply_preset()
    assert view.request().tracks == ((0, 'omit'), (1, 'aac'))
    view.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('encoder,mode', [('libx264', 'quality'), ('libx265', 'quality'), ('libx264', 'bitrate')])
def test_real_compression_modes(video_sample, encoder, mode):
    app = QApplication.instance() or QApplication([])
    binaries, base = video_sample
    if encoder not in list_encoders(binaries.ffmpeg, Event()):
        pytest.skip(f'No {encoder} in selected build')
    request = ConversionRequest(base.output.path, base.output.container, ((0, encoder), (1, 'aac')),
                                mode=mode, crf=28, preset='ultrafast', audio_quality=2)
    task = OperationTask(TaskRecord(conversion_plan(base.media, request)), binaries)
    results = []
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.status == TaskStatus.COMPLETED, task.record.error + task.record.log
    assert task.record.result.streams[0].codec == ('hevc' if encoder == 'libx265' else 'h264')


def test_failed_encode_has_no_published_output(video_sample, monkeypatch):
    app = QApplication.instance() or QApplication([])
    binaries, base = video_sample
    if 'libx264' not in list_encoders(binaries.ffmpeg, Event()):
        pytest.skip('No libx264')
    task = OperationTask(TaskRecord(conversion_plan(base.media, ConversionRequest(base.output.path, base.output.container, ((0, 'libx264'),)))), binaries)
    original = task._prepare
    def broken_encode():
        plan, command = original()
        command.insert(1, '-invalid-encoding-option')
        return plan, command
    monkeypatch.setattr(task, '_prepare', broken_encode)
    results = []
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.status == TaskStatus.FAILED and task.record.result is None
    assert not base.output.path.exists()


def test_unknown_encoder_and_incompatible_audio_are_rejected(sample):
    _, base = sample
    request = ConversionRequest(base.output.path, base.output.container, ((0, 'aac'),))
    plan = conversion_plan(base.media, request)
    with pytest.raises(PlanValidationError, match='unavailable'):
        CommandBuilder().build(base.media.path, plan)
    from media_wrapper.domain.remux import Container
    copied = conversion_plan(base.media, replace(request, tracks=((0, 'copy'),), container=Container.MP4,
                                                destination=base.output.path.with_suffix('.mp4')))
    with pytest.raises(PlanValidationError, match='unsupported'):
        CommandBuilder().build(base.media.path, copied)
