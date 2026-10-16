from pathlib import Path

import pytest

from media_wrapper.infrastructure.ffmpeg.binary_resolver import resolve
from media_wrapper.infrastructure.ffmpeg.probe_parser import parse_probe


def test_media_info_parses_missing_values():
    info = parse_probe(Path("test.mkv"), {"format": {"duration": "NaN?", "size": "1234"}, "streams": [{"codec_name": "h264"}]})
    assert info.duration is None
    assert info.size_bytes == 1234
    assert len(info.streams) == 1


def test_invalid_mode():
    with pytest.raises(ValueError):
        resolve("invalid")


def test_bundled_requires_path():
    with pytest.raises(ValueError):
        resolve("bundled")
