from fractions import Fraction
from pathlib import Path

from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.ui.inspection_presenter import format_inspection, stream_values
from media_wrapper.ui.view_model import DesktopViewModel


def test_all_inspection_details_and_real_indices():
    info = MediaFile(Path('test.mkv'), 'matroska', 3, 100, (
        MediaStream(4, 'video', 'h264', width=1920, height=1080, average_frame_rate=Fraction(30000, 1001)),
        MediaStream(7, 'audio', 'aac', language='eng', bit_rate=128000, channels=2, sample_rate=48000),
        MediaStream(9, 'subtitle', 'subrip', language='fra'),
    ), 1000000)
    text = format_inspection(info)
    for expected in ('Stream 4', 'Stream 7', 'Stream 9', '30000/1001 fps', '1920 × 1080',
                     '1000000 bit/s', '128000 bit/s', 'Channels: 2', 'Language: eng', 'Subtitle type: subrip'):
        assert expected in text
    assert 'Stream 0' not in text
    assert 'unknown' in stream_values(MediaStream(None))


def test_stream_selection_uses_indices_and_clears_with_file():
    model = DesktopViewModel()
    model._inspected(MediaFile(Path('test.mkv'), streams=(MediaStream(4), MediaStream(7), MediaStream(None))))
    assert model.state.selected_streams == (4, 7)
    model.select_streams((7,))
    assert model.state.selected_streams == (7,)
    model.select_streams((0,))
    assert model.state.selected_streams == (7,)
    model.select_file(Path('different.mkv'))
    assert model.state.selected_streams == ()
    assert model.state.media is None
