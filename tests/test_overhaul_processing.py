"""Release-relevant output checks using generated FFmpeg media."""
import json
import subprocess
import time
from dataclasses import replace
from fractions import Fraction
from threading import Event
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from media_wrapper.application.conversion_service import conversion_plan
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_task import OperationTask
from media_wrapper.application.operation_validation import validate_paths
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.operations import EncodingProfile, MediaOperation
from media_wrapper.domain.profile_document import parse_profile, profile_payload
from media_wrapper.domain.remux import Container
from media_wrapper.domain.target_size import size_limit
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders
from media_wrapper.infrastructure.ffmpeg.output_publication import publish_output


def run_task(plan, binaries):
    app = QApplication.instance() or QApplication([])
    task = OperationTask(TaskRecord(plan), binaries)
    done = []
    task.finished.connect(lambda *result: done.append(result))
    task.start()
    deadline = time.monotonic() + 45
    while not done and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    if not done:
        task.cancel()
        shutdown_deadline = time.monotonic() + 3
        while not done and time.monotonic() < shutdown_deadline:
            app.processEvents()
    assert done, 'Timed out waiting for real FFmpeg processing'
    return task.record


def test_size_units_and_independent_profile_roundtrip(video_sample):
    _, base = video_sample
    media = replace(base.media, duration=90, size_bytes=7_000_000)
    assert size_limit('1.25', 'MB', media) == 1_250_000
    assert size_limit('1.25', 'MiB', media) == 1_310_720
    assert size_limit('2', 'MB/min', media) == 3_000_000
    assert size_limit('2', 'MiB/min', media) == 3_145_728
    assert size_limit('25', '%', media) == 5_250_000
    with pytest.raises(ValueError):
        size_limit('100', '%', media)
    profile = EncodingProfile('libx264', fps=Fraction(30000, 1001), codec_profile='high')
    request = ConversionRequest(base.output.path, base.output.container, ((0, 'libx264'),),
                                mode='target', stream_profiles=((0, profile),), target_size=('2.5', 'MB'),
                                deep_verify=True)
    payload = json.loads(json.dumps(profile_payload(request)))
    assert parse_profile(payload, request.destination) == request
    assert conversion_plan(media, request).target_size_bytes == 2_500_000


def test_strict_limit_publishes_real_output(video_sample):
    binaries, base = video_sample
    if 'libx264' not in list_encoders(binaries.ffmpeg, Event()):
        pytest.skip('The selected FFmpeg build has no H.264 software encoder')
    original = base.media.path.read_bytes()
    request = ConversionRequest(base.output.path, base.output.container, ((0, 'libx264'), (1, 'aac')),
                                operation=MediaOperation.COMPRESS, mode='target', target_size=('0.15', 'MB'),
                                preset='ultrafast', deep_verify=True)
    result = run_task(conversion_plan(base.media, request), binaries)
    assert result.status == TaskStatus.COMPLETED, result.log
    assert len(result.commands) == 2
    assert result.result.size_bytes == base.output.path.stat().st_size <= 150_000
    assert base.media.path.read_bytes() == original


def test_strict_limit_retries_only_twice_and_keeps_oversized_output_unpublished(video_sample, monkeypatch):
    binaries, base = video_sample
    if 'libx264' not in list_encoders(binaries.ffmpeg, Event()):
        pytest.skip('The selected FFmpeg build has no H.264 software encoder')
    real_verify = OperationTask._verify_publish

    def pad_before_verification(task):
        with task.prepared.output.execution_path.open('ab') as output:
            output.write(b'\x00' * 160_000)
        return real_verify(task)

    monkeypatch.setattr(OperationTask, '_verify_publish', pad_before_verification)
    request = ConversionRequest(base.output.path, base.output.container, ((0, 'libx264'),),
                                operation=MediaOperation.COMPRESS, mode='target', target_size=('0.12', 'MB'),
                                preset='ultrafast')
    result = run_task(conversion_plan(base.media, request), binaries)
    assert result.status == TaskStatus.FAILED
    assert 'Strict size limit failed' in result.failure_detail
    assert len(result.commands) == 6
    assert not base.output.path.exists()
    assert base.media.path.is_file()


@pytest.mark.parametrize(('container', 'encoder', 'codec', 'suffix'), [
    (Container.FLAC, 'flac', 'flac', '.flac'),
    (Container.M4A, 'alac', 'alac', '.m4a'),
    (Container.M4A, 'aac', 'aac', '.m4a'),
    (Container.MP3, 'libmp3lame', 'mp3', '.mp3'),
    (Container.OPUS, 'libopus', 'opus', '.opus'),
    (Container.WAV, 'pcm_s24le', 'pcm_s24le', '.wav'),
])
def test_standalone_audio_formats(sample, tmp_path, container, encoder, codec, suffix):
    binaries, base = sample
    if encoder not in list_encoders(binaries.ffmpeg, Event()):
        pytest.skip(f'The selected FFmpeg build has no {encoder} encoder')
    path = tmp_path / ('Voice ü' + suffix)
    result = run_task(conversion_plan(base.media, ConversionRequest(path, container, ((0, encoder),))), binaries)
    assert result.status == TaskStatus.COMPLETED, result.log
    assert [(s.kind, s.codec) for s in result.result.streams] == [('audio', codec)]


def test_obs_style_av1_to_intermediate_preserves_audio_tracks(sample, tmp_path):
    binaries, _ = sample
    encoders = list_encoders(binaries.ffmpeg, Event())
    if not {'libaom-av1', 'dnxhd'} <= encoders:
        pytest.skip('The selected FFmpeg build needs libaom-av1 and dnxhd')
    source = tmp_path / 'Deadlock ゲーム.mkv'
    ffmpeg = str(binaries.ffmpeg)
    subprocess.run([
        ffmpeg, '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=30:d=2',
        '-f', 'lavfi', '-i', 'sine=frequency=320:duration=2:sample_rate=48000',
        '-f', 'lavfi', '-i', 'sine=frequency=640:duration=2:sample_rate=48000',
        '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:v', 'libaom-av1', '-strict:v', 'experimental', '-cpu-used', '8',
        '-c:a', 'aac', '-metadata:s:a:0', 'title=Game', '-metadata:s:a:1', 'title=Microphone',
        '-metadata:s:a:0', 'language=jpn', '-metadata:s:a:1', 'language=eng',
        '-n', str(source),
    ], check=True, capture_output=True, timeout=30)
    media = MediaService(binaries).inspect(source)
    assert media.streams[0].codec == 'av1'
    assert media.streams[0].bit_depth == 8
    path = tmp_path / 'Deadlock edit.mov'
    request = ConversionRequest(path, Container.MOV, ((0, 'dnxhd'), (1, 'pcm_s16le'), (2, 'pcm_s16le')),
                                codec_profile='dnxhr_sq')
    result = run_task(conversion_plan(media, request), binaries)
    assert result.status == TaskStatus.COMPLETED, result.log
    video, game, mic = result.result.streams
    assert (video.codec, video.width, video.height, video.frame_rate) == ('dnxhd', 320, 180, 30)
    assert [(s.codec, s.title, s.language) for s in (game, mic)] == [
        ('pcm_s16le', 'Game', 'jpn'), ('pcm_s16le', 'Microphone', 'eng'),
    ]


def test_output_collision_and_disk_space(sample, tmp_path, monkeypatch):
    _, base = sample
    monkeypatch.setattr('media_wrapper.application.operation_validation.shutil.disk_usage',
                        lambda path: SimpleNamespace(free=0))
    with pytest.raises(ValueError, match='Insufficient free space'):
        validate_paths(base)
    staged, destination = tmp_path / 'stage.mkv', tmp_path / 'collision.mkv'
    staged.write_bytes(b'new media')
    destination.write_bytes(b'keep')
    with pytest.raises(FileExistsError):
        publish_output(staged, destination)
    assert staged.read_bytes() == b'new media'
    assert destination.read_bytes() == b'keep'


def test_explicit_sdr_conversion_is_applied_and_verified(sample, tmp_path):
    binaries, _ = sample
    if not {'libx264', 'ffv1'} <= list_encoders(binaries.ffmpeg, Event()):
        pytest.skip('The selected FFmpeg build needs libx264 and ffv1')
    source = tmp_path / 'BT709.mkv'
    subprocess.run([
        str(binaries.ffmpeg), '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
        'testsrc2=s=96x64:r=10:d=1',
        '-vf', 'setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709',
        '-c:v', 'libx264', '-x264-params', 'colorprim=bt709:transfer=bt709:colormatrix=bt709',
        '-n', str(source),
    ], check=True, capture_output=True, timeout=15)
    media = MediaService(binaries).inspect(source)
    path = tmp_path / 'SMPTE170M.mkv'
    profile = EncodingProfile('ffv1', color_space='smpte170m', color_transfer='smpte170m',
                              color_primaries='smpte170m')
    result = run_task(conversion_plan(media, ConversionRequest(
        path, Container.MATROSKA, ((0, 'ffv1'),), stream_profiles=((0, profile),),
    )), binaries)
    assert result.status == TaskStatus.COMPLETED, result.log
    output = result.result.streams[0]
    assert (output.color_space, output.color_transfer, output.color_primaries) == ('smpte170m',) * 3
    assert any(argument.startswith('colorspace=space=smpte170m') for argument in result.command)
