"""Versioned encoding choices, without source/destination or executable paths."""
from dataclasses import asdict, fields
from fractions import Fraction
from pathlib import Path
from typing import Any

from media_wrapper.domain.capabilities import GPU_ENCODERS
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.custom_options import parse_custom_options
from media_wrapper.domain.operation_policy import ENCODERS
from media_wrapper.domain.operations import (
    EncodingProfile,
    MediaOperation,
    PreservationPolicy,
)
from media_wrapper.domain.remux import Container
from media_wrapper.domain.target_size import SIZE_UNITS

_ADDED_KEYS = {'codec_profile', 'pixel_format', 'stream_profiles', 'target_size', 'deep_verify'}


def profile_payload(request: ConversionRequest) -> dict[str, Any]:
    settings = asdict(request)
    settings.pop('destination')
    settings['tracks'] = [list(track) for track in request.tracks]
    settings['track_order'] = list(request.track_order)
    settings['stream_profiles'] = [
        [index, dict(asdict(profile), fps=str(profile.fps) if profile.fps else None)]
        for index, profile in request.stream_profiles
    ]
    settings['target_size'] = list(request.target_size) if request.target_size else None
    settings['container'] = request.container.value
    settings['operation'] = request.operation.value
    return {'kind': 'media-wrapper-profile', 'version': 1, 'settings': settings}


def parse_profile(payload: Any, destination: Path) -> ConversionRequest:
    if not isinstance(payload, dict) or set(payload) != {'kind', 'version', 'settings'} or payload['kind'] != 'media-wrapper-profile' or type(payload['version']) is not int or payload['version'] != 1:
        raise ValueError('Unsupported profile schema/version')
    data = payload['settings']
    defaults = asdict(ConversionRequest(destination, Container.MATROSKA, ()))
    defaults.pop('destination')
    if not isinstance(data, dict) or not set(defaults) - _ADDED_KEYS <= set(data) <= set(defaults):
        raise ValueError('Missing or unknown profile settings')
    data = {**defaults, **data}
    if 'stream_profiles' not in payload['settings']:
        data['stream_profiles'] = []
    for key in ('codec_profile', 'pixel_format'):
        if data[key] is not None and (not isinstance(data[key], str) or len(data[key]) > 48):
            raise ValueError(f'Invalid {key}')
    if type(data['deep_verify']) is not bool:
        raise ValueError('Invalid deep verification policy')
    size = data['target_size']
    if size is not None and (
        not isinstance(size, list) or len(size) != 2 or not isinstance(size[0], str)
        or len(size[0]) > 32 or size[1] not in SIZE_UNITS
    ):
        raise ValueError('Invalid target size')
    data['target_size'] = tuple(size) if size else None
    data['stream_profiles'] = _parse_stream_profiles(data['stream_profiles'])
    for key in ('width', 'height', 'audio_quality', 'target_size_bytes'):
        if data[key] is not None and type(data[key]) is not int:
            raise ValueError(f'Invalid {key}')
    for key in ('audio_bitrate', 'crf', 'video_bitrate'):
        if type(data[key]) is not int:
            raise ValueError(f'Invalid {key}')
    for key in ('fps', 'mode', 'preset', 'hardware_mode', 'gpu_encoder'):
        if not isinstance(data[key], str) or len(data[key]) > 128 or '\x00' in data[key]:
            raise ValueError(f'Invalid {key}')
    if data['mode'] not in {'default', 'quality', 'bitrate', 'target'} or data['hardware_mode'] not in {'CPU', 'GPU', 'Auto', 'Prefer GPU'}:
        raise ValueError('Invalid profile mode')
    if data['gpu_encoder'] not in {'auto', *GPU_ENCODERS}:
        raise ValueError('Unsupported GPU preference')
    parse_custom_options(data['custom_arguments'])
    for key, low, high, step in (('width', 2, 16384, 2), ('height', 2, 16384, 2),
                                 ('audio_bitrate', 8000, 512000, 1000), ('video_bitrate', 32000, 200000000, 1000),
                                 ('crf', 0, 51, 1), ('audio_quality', 1, 5, 1),
                                 ('target_size_bytes', 1, 2**63 - 1, 1)):
        value = data[key]
        if value is not None and (not low <= value <= high or value % step):
            raise ValueError(f'Profile {key} cannot be represented by the form')
    if data['preset'] not in {'ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'}:
        raise ValueError('Unsupported profile preset')
    tracks = data['tracks']
    if not isinstance(tracks, list) or len(tracks) > 256:
        raise ValueError('Invalid profile tracks')
    for track in tracks:
        if not isinstance(track, list) or len(track) != 2 or type(track[0]) is not int or track[0] < 0 or not isinstance(track[1], str) or track[1] not in {'copy', 'omit', *(set(ENCODERS) - set(GPU_ENCODERS))}:
            raise ValueError('Invalid track index or encoder')
    if len({t[0] for t in tracks}) != len(tracks):
        raise ValueError('Duplicate profile track index')
    order = data['track_order']
    if not isinstance(order, list) or any(type(i) is not int or i < 0 for i in order) or len(set(order)) != len(order):
        raise ValueError('Invalid track order')
    data['track_order'] = tuple(order)
    data['metadata_policy'] = PreservationPolicy(data['metadata_policy'])
    data['chapter_policy'] = PreservationPolicy(data['chapter_policy'])
    data['tracks'] = tuple(tuple(t) for t in tracks)
    data['container'] = Container(data['container'])
    data['operation'] = MediaOperation(data['operation'])
    if data['operation'] == MediaOperation.REMUX:
        raise ValueError('Encoding profiles require Convert or Compress')
    return ConversionRequest(destination=destination, **data)



def _parse_stream_profiles(value: Any) -> tuple[tuple[int, EncodingProfile], ...]:
    if not isinstance(value, list) or len(value) > 256:
        raise ValueError('Invalid stream profiles')
    permitted = {field.name for field in fields(EncodingProfile)}
    found = set()
    profiles = []
    for row in value:
        if (
            not isinstance(row, list) or len(row) != 2 or type(row[0]) is not int or row[0] < 0
            or row[0] in found or not isinstance(row[1], dict) or not set(row[1]) <= permitted
        ):
            raise ValueError('Invalid or duplicate stream profile')
        index, profile = row[0], dict(row[1])
        for key, option in profile.items():
            if option is not None and type(option) not in {int, str}:
                raise ValueError(f'Invalid stream profile {key}')
        if profile.get('fps') is not None:
            profile['fps'] = Fraction(profile['fps'])
        found.add(index)
        profiles.append((index, EncodingProfile(**profile)))
    return tuple(profiles)
