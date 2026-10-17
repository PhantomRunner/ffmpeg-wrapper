"""Translate optional FFprobe metadata into typed domain entities."""
import math
from fractions import Fraction
from pathlib import Path
from typing import Any

from media_wrapper.domain.media import MediaChapter, MediaFile, MediaStream


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value and value != 'N/A' else None


def _integer(value: Any, minimum: int = 0) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    try:
        result = int(value)
        return result if result >= minimum else None
    except ValueError:
        return None


def _duration(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _rate(value: Any) -> Fraction | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    try:
        result = Fraction(value)
        return result if result > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def parse_probe(path: Path, payload: Any) -> MediaFile:
    if not isinstance(payload, dict):
        raise ValueError('Invalid FFprobe metadata structure')  # noqa: TRY004 - invalid serialized value
    fmt, streams = payload.get('format'), payload.get('streams')
    fmt = {} if fmt is None else fmt
    streams = [] if streams is None else streams
    if not isinstance(fmt, dict) or not isinstance(streams, list):
        raise ValueError('Invalid FFprobe metadata structure')  # noqa: TRY004 - invalid serialized value
    parsed = tuple(_stream(stream) for stream in streams)
    indices = [stream.index for stream in parsed if stream.index is not None]
    if len(indices) != len(set(indices)):
        raise ValueError('FFprobe returned duplicate stream indices')
    tags = fmt.get('tags') or {}
    chapters = payload.get('chapters') or []
    if not isinstance(tags, dict) or not isinstance(chapters, list) or any(not isinstance(c, dict) for c in chapters):
        raise ValueError('Invalid container tags or chapters')
    parsed_chapters = []
    for chapter in chapters:
        chapter_tags = chapter.get('tags') or {}
        if not isinstance(chapter_tags, dict):
            raise ValueError('Invalid chapter tags')
        parsed_chapters.append(MediaChapter(_duration(chapter.get('start_time')), _duration(chapter.get('end_time')), _text(chapter_tags.get('title'))))
    return MediaFile(path, _text(fmt.get('format_name')) or 'unknown', _duration(fmt.get('duration')),
                     _integer(fmt.get('size')), parsed, _integer(fmt.get('bit_rate')),
                     tuple((str(k), v) for k, v in tags.items() if isinstance(v, str)), tuple(parsed_chapters))


def _stream(payload: Any) -> MediaStream:
    if not isinstance(payload, dict):
        raise ValueError('Invalid FFprobe stream structure')  # noqa: TRY004 - invalid serialized value
    index = payload.get('index')
    if index is not None and (type(index) is not int or index < 0):
        raise ValueError('FFprobe stream index must be a nonnegative integer')
    tags = payload.get('tags')
    tags = {} if tags is None else tags
    if not isinstance(tags, dict):
        raise ValueError('Invalid FFprobe stream tags')  # noqa: TRY004 - invalid serialized value
    return MediaStream(
        index=index, kind=_text(payload.get('codec_type')) or 'unknown',
        codec=_text(payload.get('codec_name')) or 'unknown', codec_long_name=_text(payload.get('codec_long_name')),
        language=_text(tags.get('language')), title=_text(tags.get('title')), bit_rate=_integer(payload.get('bit_rate')),
        width=_integer(payload.get('width'), 1), height=_integer(payload.get('height'), 1),
        average_frame_rate=_rate(payload.get('avg_frame_rate')), nominal_frame_rate=_rate(payload.get('r_frame_rate')),
        sample_rate=_integer(payload.get('sample_rate'), 1), channels=_integer(payload.get('channels'), 1),
        channel_layout=_text(payload.get('channel_layout')),
    )
