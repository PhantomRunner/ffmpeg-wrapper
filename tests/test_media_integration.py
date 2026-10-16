"""M2 end-to-end inspection fixtures: audio, video, multiple tracks and errors."""
import subprocess
import threading
import time
from fractions import Fraction

import pytest
from PySide6.QtWidgets import QApplication

from media_wrapper.application.errors import ApplicationError
from media_wrapper.application.media_service import MediaService
from media_wrapper.domain.inspection import InspectionStatus as Status
from media_wrapper.infrastructure.ffmpeg.binary_resolver import resolve
from media_wrapper.ui.view_model import DesktopViewModel


@pytest.fixture(scope='module')
def media_samples(tmp_path_factory):
    try:
        binaries = resolve()
    except (FileNotFoundError, RuntimeError) as error:
        pytest.skip(str(error))
    root = tmp_path_factory.mktemp('inspection ü samples')
    subtitle = root/'captions.srt'
    subtitle.write_text('1\n00:00:00,000 --> 00:00:00,200\nBonjour\n', encoding='utf-8')
    audio, video, multi = root/'audio ü.wav', root/'video only.mkv', root/'many tracks.mkv'
    base = [str(binaries.ffmpeg), '-v', 'error', '-nostdin', '-n']
    video_input = ['-f', 'lavfi', '-i', 'color=c=black:s=64x48:r=30000/1001:d=0.2']
    audio_input = ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.2']
    commands = [
        base + audio_input + ['-c:a', 'pcm_s16le', str(audio)],
        base + video_input + ['-c:v', 'ffv1', '-an', str(video)],
        base + video_input + audio_input + ['-f', 'srt', '-i', str(subtitle),
            '-map', '0:v:0', '-map', '1:a:0', '-map', '1:a:0', '-map', '2:s:0',
            '-c:v', 'ffv1', '-c:a', 'pcm_s16le', '-c:s', 'srt',
            '-metadata:s:a:0', 'language=eng', '-metadata:s:a:1', 'language=jpn',
            '-metadata:s:s:0', 'language=fra', '-t', '0.2', str(multi)],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, timeout=15)
    return binaries, (audio, video, multi)


def test_real_audio_and_video_only(media_samples):
    binaries, (audio, video, _) = media_samples
    service = MediaService(binaries)
    audio_info = service.inspect(audio, threading.Event())
    assert [s.kind for s in audio_info.streams] == ['audio']
    assert audio_info.streams[0].codec == 'pcm_s16le'
    assert audio_info.streams[0].channels == 1
    assert audio_info.streams[0].sample_rate == 44100
    assert audio_info.size_bytes == audio.stat().st_size
    video_info = service.inspect(video, threading.Event())
    assert [s.kind for s in video_info.streams] == ['video']
    stream = video_info.streams[0]
    assert stream.width == 64 and stream.height == 48
    assert stream.frame_rate == Fraction(30000, 1001)


def test_real_multitrack_and_subtitle_languages(media_samples):
    binaries, (_, _, multi) = media_samples
    info = MediaService(binaries).inspect(multi, threading.Event())
    assert [s.index for s in info.streams] == [0, 1, 2, 3]
    assert [s.kind for s in info.streams] == ['video', 'audio', 'audio', 'subtitle']
    assert [s.language for s in info.streams[1:]] == ['eng', 'jpn', 'fra']
    assert info.streams[3].codec == 'subrip'


def test_real_invalid_media_is_an_actionable_failure(media_samples, tmp_path):
    binaries, _ = media_samples
    bad = tmp_path/'not-media.mkv'
    bad.write_bytes(b'not a media container')
    with pytest.raises(ApplicationError, match='process failed') as failure:
        MediaService(binaries).inspect(bad, threading.Event())
    assert failure.value.__cause__ is not None
    assert bad.read_bytes() == b'not a media container'


def test_actual_batch_failure_isolation_and_cached_selection(media_samples, tmp_path):
    app = QApplication.instance() or QApplication([])
    binaries, files = media_samples
    bad = tmp_path/'bad file'
    bad.write_bytes(b'invalid')
    model = DesktopViewModel()
    model.state.binaries = binaries
    model.add_files([files[0], bad, files[1], files[2]])
    model.inspect_many(model.state.files)
    deadline = time.monotonic() + 15
    while model.state.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.001)
    assert not model.state.busy
    assert [model.state.inspections[p].status for p in model.state.files] == [Status.COMPLETED, Status.FAILED, Status.COMPLETED, Status.COMPLETED]
    model.select_file(files[2])
    assert len(model.state.media.streams) == 4
    model.select_streams((1, 3))
    model.select_file(bad)
    assert model.state.media is None and model.state.source is None
    assert 'failed' in model.state.output.lower()
    model.select_file(files[2])
    assert model.state.selected_streams == (1, 3)
    assert '3 completed, 1 failed' in model.state.inspection_summary
