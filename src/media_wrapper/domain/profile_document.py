"""Versioned encoding choices, without source/destination or executable paths."""
from dataclasses import asdict
from pathlib import Path
from typing import Any

from media_wrapper.domain.capabilities import GPU_ENCODERS
from media_wrapper.domain.custom_options import parse_custom_options
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.operation_policy import ENCODERS
from media_wrapper.domain.operations import MediaOperation, PreservationPolicy
from media_wrapper.domain.remux import Container


def profile_payload(request: ConversionRequest) -> dict[str, Any]:
    settings = asdict(request)
    settings.pop('destination')
    settings['tracks'] = [list(track) for track in request.tracks]
    settings['track_order'] = list(request.track_order)
    settings['container'] = request.container.value
    settings['operation'] = request.operation.value
    return {'kind': 'media-wrapper-profile', 'version': 1, 'settings': settings}


def parse_profile(payload: Any, destination: Path) -> ConversionRequest:
    if not isinstance(payload, dict) or set(payload) != {'kind', 'version', 'settings'} or payload['kind'] != 'media-wrapper-profile' or type(payload['version']) is not int or payload['version'] != 1:
        raise ValueError('Unsupported profile schema/version')
    data = payload['settings']
    defaults = asdict(ConversionRequest(destination, Container.MATROSKA, ()))
    defaults.pop('destination')
    if not isinstance(data, dict) or set(data) != set(defaults):
        raise ValueError('Missing or unknown profile settings')
    data = dict(data)
    for key in ('width', 'height', 'audio_quality', 'target_size_bytes'):
        if data[key] is not None and type(data[key]) is not int:
            raise ValueError(f'Invalid {key}')
    for key in ('audio_bitrate', 'crf', 'video_bitrate'):
        if type(data[key]) is not int:
            raise ValueError(f'Invalid {key}')
    for key in ('fps', 'mode', 'preset', 'hardware_mode', 'gpu_encoder'):
        if not isinstance(data[key], str) or len(data[key]) > 128 or '\x00' in data[key]:
            raise ValueError(f'Invalid {key}')
    if data['mode'] not in {'default', 'quality', 'bitrate', 'target'} or data['hardware_mode'] not in {'CPU', 'GPU', 'Auto'}:
        raise ValueError('Invalid profile mode')
    if data['gpu_encoder'] not in {'auto', *GPU_ENCODERS}:
        raise ValueError('Unsupported GPU preference')
    parse_custom_options(data['custom_arguments'])
    tracks = data['tracks']
    if not isinstance(tracks, list) or len(tracks) > 256:
        raise ValueError('Invalid profile tracks')
    for track in tracks:
        if not isinstance(track, list) or len(track) != 2 or type(track[0]) is not int or track[0] < 0 or not isinstance(track[1], str) or track[1] not in {'copy', 'omit', *ENCODERS}:
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
    return ConversionRequest(destination=destination, **data)
