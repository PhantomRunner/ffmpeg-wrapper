import subprocess
import time

import pytest
from PySide6.QtWidgets import QApplication

from media_wrapper.application.playback_service import PlaybackService
from media_wrapper.ui.panels.media_timeline import MediaTimeline
from media_wrapper.ui.panels.playback import PlaybackPanel


def wait(app, predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert predicate()


@pytest.mark.parametrize('video', [False, True])
def test_real_play_pause_seek_end_and_release(sample, tmp_path, video):
    binaries, _ = sample
    app = QApplication.instance() or QApplication([])
    path = tmp_path / ('preview.mp4' if video else 'preview.wav')
    args = ['-f', 'lavfi', '-i', 'testsrc2=s=96x64:r=10:d=2', '-c:v', 'mpeg4'] if video else [
        '-f', 'lavfi', '-i', 'sine=duration=2']
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', *args, '-n', str(path)],
                   check=True, capture_output=True, timeout=15)
    panel = PlaybackPanel()
    panel.show()
    service = panel.service
    assert service is not None
    frames = []
    if video:
        panel.video.videoSink().videoFrameChanged.connect(lambda frame: frames.append(frame.isValid()))
    panel.set_source(path)
    wait(app, lambda: service.ready or service.error)
    assert not service.error
    assert service.duration >= 1900 and service.seekable
    panel.play.click()
    wait(app, lambda: service.position > 100)
    panel.play.click()
    assert not service.playing
    service.seek(1000)
    wait(app, lambda: abs(service.position - 1000) < 100)
    panel.play.click()
    wait(app, lambda: not service.playing and service.position >= 1900)
    if video:
        assert any(frames)
    panel.set_source(tmp_path / 'missing.mkv')
    wait(app, lambda: bool(service.error))
    assert not panel.play.isEnabled() and 'Playback error' in panel.status.text()
    panel.set_source(path)
    wait(app, lambda: service.ready)
    assert not service.error
    panel.shutdown()
    assert service.backend.player.source().isEmpty()
    panel.close()


def test_timeline_playhead_seek_and_source_reset(tmp_path):
    from media_wrapper.domain.media import MediaFile, MediaStream
    app = QApplication.instance() or QApplication([])
    panel = MediaTimeline()
    panel.set_media(MediaFile(tmp_path / 'source.mkv', duration=10,
                              streams=(MediaStream(0, 'video', 'h264'),)))
    panel.set_position(2500)
    assert panel.playhead.x() == 200
    requested = []
    panel.seek_requested.connect(requested.append)
    panel.seek_fraction(.6)
    assert requested == [6000]
    panel.set_media(None)
    panel.set_position(100)
    assert panel.playhead is None
    panel.close()
    app.processEvents()


def test_invalid_media_and_empty_source(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / 'broken.mp4'
    path.write_text('not media')
    service = PlaybackService()
    service.set_source(path)
    wait(app, lambda: bool(service.error))
    assert not service.ready
    service.set_source(None)
    assert not service.error and not service.ready and service.position == 0
    service.close()
