import pytest

from media_wrapper.infrastructure.ffmpeg.progress_parser import ProgressParser


def test_chunked_progress_estimates():
    parser = ProgressParser(10)
    assert parser.feed(b'out_time_us=250') == []
    progress, = parser.feed(b'0000\nspeed=2x\nprogress=continue\n')
    assert progress.seconds == 2.5 and progress.percent == 25
    assert progress.eta == 3.75 and not progress.ended
    end, = parser.feed(b'out_time_ms=12000000\nprogress=end\n')
    assert end.percent == 100 and end.ended


@pytest.mark.parametrize('duration', [None, 0, -1, float('nan')])
def test_unknown_duration_never_invents_percentage(duration):
    result, = ProgressParser(duration).feed(b'out_time_us=5000000\nspeed=N/A\nprogress=end\n')
    assert result.percent is None and result.eta is None and result.speed is None


def test_malformed_bounded_progress():
    parser = ProgressParser(10)
    parser.feed(b'x' * 100000)
    assert len(parser.buffer) <= 4096
    result, = parser.feed(b'\nout_time_us=NaN\nspeed=infx\nprogress=end\n')
    assert result.seconds is None and result.speed is None
