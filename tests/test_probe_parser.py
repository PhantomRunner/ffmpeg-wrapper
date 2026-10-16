from fractions import Fraction
from pathlib import Path

import pytest

from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.infrastructure.ffmpeg.probe_parser import parse_probe


def test_typed_multitrack_metadata_and_exact_rates():
    info = parse_probe(Path('sample.mkv'), {'format': {'format_name': 'matroska', 'duration': '1.25', 'size': '123', 'bit_rate': '456'},
        'streams': [{'index': 2, 'codec_type': 'video', 'codec_name': 'h264', 'width': 1920, 'height': 1080,
                     'avg_frame_rate': '30000/1001', 'r_frame_rate': '30/1'},
                    {'index': 5, 'codec_type': 'audio', 'codec_name': 'aac', 'sample_rate': '48000', 'channels': 2,
                     'channel_layout': 'stereo', 'tags': {'language': 'eng', 'title': 'Main'}},
                    {'index': 9, 'codec_type': 'subtitle', 'codec_name': 'subrip', 'tags': {'language': 'fra'}}]})
    assert isinstance(info, MediaFile)
    assert all(isinstance(stream, MediaStream) for stream in info.streams)
    assert info.bit_rate == 456 and info.duration == 1.25
    assert info.streams[0].frame_rate == Fraction(30000, 1001)
    assert info.streams[1].sample_rate == 48000 and info.streams[1].language == 'eng'
    assert info.streams[2].index == 9 and info.streams[2].codec == 'subrip'


@pytest.mark.parametrize('value', ['0/0', '1/0', 'N/A', 'NaN', '-1/2', True, None])
def test_unknown_rates_are_safe_and_fall_back(value):
    stream = parse_probe(Path('x'), {'streams': [{'index': 0, 'avg_frame_rate': value, 'r_frame_rate': '24/1'}]}).streams[0]
    assert stream.average_frame_rate is None
    assert stream.frame_rate == Fraction(24)


def test_absent_fields_are_unknown_not_invented():
    info = parse_probe(Path('x'), {'streams': [{}]})
    assert info.streams == (MediaStream(None),)
    assert info.duration is None and info.size_bytes is None
    assert info.streams[0].frame_rate is None


@pytest.mark.parametrize('streams', [[{'index': True}], [{'index': '1'}], [{'index': -1}],
                                    [{'index': 2}, {'index': 2}], [{'tags': []}]])
def test_invalid_stream_identity_and_structure(streams):
    with pytest.raises(ValueError):
        parse_probe(Path('x'), {'streams': streams})


def test_invalid_optional_numeric_values_are_unknown():
    info = parse_probe(Path('x'), {'format': {'size': True, 'duration': 'nan', 'bit_rate': '2.4'},
                                 'streams': [{'width': 0, 'channels': -1, 'sample_rate': 'N/A'}]})
    assert info.size_bytes is None and info.duration is None and info.bit_rate is None
    assert info.streams[0].width is None and info.streams[0].channels is None
