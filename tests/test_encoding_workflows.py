from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from media_wrapper.application.size_estimate import estimate_output
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.remux import Container
from media_wrapper.ui.encoding_view import EncodingView


def test_primary_controls_differ_and_requests_remain_editable(tmp_path):
    app = QApplication.instance() or QApplication([])
    media = MediaFile(tmp_path / 'source.mkv', duration=60,
                      streams=(MediaStream(0, 'video', 'h264'), MediaStream(1, 'audio', 'aac')))
    convert, compress = EncodingView(), EncodingView('Compress')
    for view in (convert, compress):
        view.set_media(media, False)
        view.show()
    app.processEvents()
    assert convert.video_width.isVisible() and convert.fps.isVisible()
    assert not convert.crf.isVisible()
    assert compress.crf.isVisible() and compress.target_size.isVisible()
    assert not compress.fps.isVisible()
    compress.mode.setCurrentText('target')
    assert compress.target_size.isEnabled() and not compress.crf.isEnabled()
    assert 'Two-pass video' in compress.estimate.text()
    compress.advanced_toggle.setChecked(True)
    assert compress.tracks.isVisible() and compress.fps.isVisible()
    compress._encoders[0].setCurrentText('copy')
    assert 'requires libx264' in compress.estimate.text()
    convert.close()
    compress.close()


@pytest.mark.parametrize('mode,expected', [('quality', 'Size varies'), ('bitrate', '15.5 MiB'), ('target', '100.0 MiB')])
def test_estimates_use_selected_rates_and_target_policy(mode, expected):
    media = MediaFile(Path('/source.mkv'), duration=60,
                      streams=(MediaStream(0, 'video', 'h264'), MediaStream(1, 'audio', 'aac')))
    request = ConversionRequest(Path('/out.mkv'), Container.MATROSKA,
                                ((0, 'libx264'), (1, 'aac')), mode=mode,
                                video_bitrate=2000000, audio_bitrate=128000,
                                target_size_bytes=104857600 if mode == 'target' else None)
    assert expected in estimate_output(media, request)
