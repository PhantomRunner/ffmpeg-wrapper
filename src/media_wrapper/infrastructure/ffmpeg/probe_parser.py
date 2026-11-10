"""Translate optional FFprobe metadata into typed domain entities."""
import json
import math
import re
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
    tags = fmt.get('tags')
    tags = {} if tags is None else tags
    chapters = payload.get('chapters')
    chapters = [] if chapters is None else chapters
    if not isinstance(tags, dict) or not isinstance(chapters, list) or any(not isinstance(c, dict) for c in chapters):
        raise ValueError('Invalid container tags or chapters')
    parsed_chapters = []
    for chapter in chapters:
        chapter_tags = chapter.get('tags')
        chapter_tags = {} if chapter_tags is None else chapter_tags
        if not isinstance(chapter_tags, dict):
            raise ValueError('Invalid chapter tags')  # noqa: TRY004 - invalid serialized value
        parsed_chapters.append(MediaChapter(_duration(chapter.get('start_time')), _duration(chapter.get('end_time')), _text(chapter_tags.get('title'))))
    return MediaFile(path, _text(fmt.get('format_name')) or 'unknown', _duration(fmt.get('duration')),
                     _integer(fmt.get('size')), parsed, _integer(fmt.get('bit_rate')),
                     tuple((str(k), v) for k, v in tags.items() if isinstance(v, str)), tuple(parsed_chapters))


def _stream_duration(value: Any, tags: dict[str, Any]) -> float | None:
    duration = _duration(value)
    if duration is not None:
        return duration
    raw = next((v for k, v in tags.items() if k.lower() == 'duration'), None)
    if isinstance(raw, str):
        parts = raw.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = map(_duration, parts)
            if None not in (hours, minutes, seconds):
                return hours * 3600 + minutes * 60 + seconds
    return None


def _color(value: Any) -> str | None:
    text = _text(value)
    return None if text in {'unknown', 'reserved', 'unspecified'} else text


def _pixel_depth(payload: dict[str, Any], pixel_format: str | None) -> int | None:
    bits = _integer(payload.get('bits_per_raw_sample'), 1) or _integer(payload.get('bits_per_sample'), 1)
    if bits or not pixel_format:
        return bits
    high = re.search(r'(9|10|12|14|16)(?:le|be)$', pixel_format)
    if high:
        return int(high[1])
    if pixel_format in {'p010le', 'p010be', 'p210le', 'p410le'}:
        return 10
    if pixel_format in {'p012le', 'p012be'}:
        return 12
    if pixel_format.startswith(('yuv', 'gbr')) or pixel_format in {'gray', 'rgb24', 'bgr24', 'nv12', 'nv21'}:
        return 8
    return None


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
    title = _text(tags.get('title'))
    handler_name = _text(tags.get('handler_name'))
    if title is None and handler_name not in {'SoundHandler', 'VideoHandler', 'SubtitleHandler', 'DataHandler'}:
        title = handler_name
    pixel_format = _text(payload.get('pix_fmt'))
    dispositions = payload.get('disposition')
    side_data = payload.get('side_data_list')
    return MediaStream(
        index=index, kind=_text(payload.get('codec_type')) or 'unknown',
        codec=_text(payload.get('codec_name')) or 'unknown', codec_long_name=_text(payload.get('codec_long_name')),
        language=_text(tags.get('language')), title=title, bit_rate=_integer(payload.get('bit_rate')),
        width=_integer(payload.get('width'), 1), height=_integer(payload.get('height'), 1),
        average_frame_rate=_rate(payload.get('avg_frame_rate')), nominal_frame_rate=_rate(payload.get('r_frame_rate')),
        sample_rate=_integer(payload.get('sample_rate'), 1), channels=_integer(payload.get('channels'), 1),
        channel_layout=_text(payload.get('channel_layout')), codec_tag=_text(payload.get('codec_tag_string')),
        profile=_text(payload.get('profile')), pixel_format=pixel_format, bit_depth=_pixel_depth(payload, pixel_format),
        sample_aspect_ratio=_text(payload.get('sample_aspect_ratio')), display_aspect_ratio=_text(payload.get('display_aspect_ratio')),
        color_space=_color(payload.get('color_space')), color_transfer=_color(payload.get('color_transfer')),
        color_primaries=_color(payload.get('color_primaries')), color_range=_color(payload.get('color_range')),
        dispositions=tuple(key for key, enabled in dispositions.items() if enabled == 1) if isinstance(dispositions, dict) else None,
        tags=tuple((str(k), v) for k, v in tags.items() if isinstance(v, str)),
        side_data=tuple(json.dumps(item, sort_keys=True) for item in side_data if isinstance(item, dict)) if isinstance(side_data, list) else (),
        duration=_stream_duration(payload.get('duration'), tags),
    )
