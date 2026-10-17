"""Versioned queue definitions contain intent, never process state or executables."""
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path

from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import (
    EncodingProfile, MediaOperation, OperationPlan, OutputTarget, PreservationPolicy, StreamSelection,
)
from media_wrapper.domain.remux import Container


def plan_payload(plan: OperationPlan, fingerprint: tuple[int, int]) -> dict:
    streams = []
    for selection in plan.streams:
        profile = asdict(selection.profile)
        profile['fps'] = str(selection.profile.fps) if selection.profile.fps is not None else None
        streams.append({'index': selection.index, 'profile': profile})
    return {'source': str(plan.media.path), 'fingerprint': list(fingerprint),
            'destination': str(plan.output.path), 'container': plan.output.container.value,
            'operation': plan.operation.value, 'streams': streams,
            'target_size_bytes': plan.target_size_bytes, 'two_pass': plan.two_pass,
            'hardware_device': plan.hardware_device, 'metadata_policy': plan.metadata_policy.value,
            'chapter_policy': plan.chapter_policy.value, 'custom_options': [list(pair) for pair in plan.custom_options]}


def parse_definition(data: object, media: MediaFile) -> OperationPlan:
    keys = {'source', 'fingerprint', 'destination', 'container', 'operation', 'streams',
            'target_size_bytes', 'two_pass', 'hardware_device', 'metadata_policy', 'chapter_policy', 'custom_options'}
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError('Missing or unknown queue definition fields')
    for key in ('source', 'destination', 'hardware_device'):
        value = data[key]
        if key == 'hardware_device' and value is None:
            continue
        if not isinstance(value, str) or not value or len(value) > 32768 or '\x00' in value:
            raise ValueError(f'Invalid queue {key}')
    if not Path(data['source']).is_absolute() or not Path(data['destination']).is_absolute():
        raise ValueError('Saved queue paths must be absolute on this operating system')
    fingerprint = data['fingerprint']
    if not isinstance(fingerprint, list) or len(fingerprint) != 2 or any(type(v) is not int for v in fingerprint) or fingerprint[0] < 0:
        raise ValueError('Invalid source fingerprint')
    if type(data['two_pass']) is not bool or (data['target_size_bytes'] is not None and type(data['target_size_bytes']) is not int):
        raise ValueError('Invalid saved rate control')
    options = data['custom_options']
    if not isinstance(options, list) or any(not isinstance(p, list) or len(p) != 2 or any(not isinstance(v, str) for v in p) for p in options):
        raise ValueError('Invalid custom options')
    streams = data['streams']
    if not isinstance(streams, list) or not 1 <= len(streams) <= 256:
        raise ValueError('Invalid saved stream selection')
    selections = []
    for stream in streams:
        if not isinstance(stream, dict) or set(stream) != {'index', 'profile'} or type(stream['index']) is not int:
            raise ValueError('Invalid saved stream')
        profile = stream['profile']
        if not isinstance(profile, dict) or set(profile) != set(asdict(EncodingProfile())):
            raise ValueError('Invalid saved encoding profile')
        profile = dict(profile)
        for key in ('bitrate', 'width', 'height', 'crf', 'audio_quality'):
            if profile[key] is not None and type(profile[key]) is not int:
                raise ValueError(f'Invalid encoding {key}')
        if not isinstance(profile['encoder'], str) or (profile['preset'] is not None and not isinstance(profile['preset'], str)):
            raise ValueError('Invalid saved encoder/preset')
        if profile['fps'] is not None:
            if not isinstance(profile['fps'], str) or len(profile['fps']) > 64:
                raise ValueError('Invalid saved frame rate')
            try:
                profile['fps'] = Fraction(profile['fps'])
            except (ValueError, ZeroDivisionError) as error:
                raise ValueError('Invalid saved frame rate') from error
        selections.append(StreamSelection(stream['index'], EncodingProfile(**profile)))
    return OperationPlan(MediaOperation(data['operation']), media, tuple(selections),
                         OutputTarget(Path(data['destination']), Container(data['container'])),
                         data['target_size_bytes'], data['two_pass'], data['hardware_device'],
                         metadata_policy=PreservationPolicy(data['metadata_policy']),
                         chapter_policy=PreservationPolicy(data['chapter_policy']),
                         custom_options=tuple(tuple(p) for p in options))


def queue_entries(payload: object) -> list[dict]:
    if not isinstance(payload, dict) or set(payload) != {'kind', 'version', 'jobs'} or payload['kind'] != 'media-wrapper-queue' or type(payload['version']) is not int or payload['version'] != 1:
        raise ValueError('Unsupported queue schema/version')
    jobs = payload['jobs']
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 1000 or any(not isinstance(j, dict) for j in jobs):
        raise ValueError('Queue must contain 1–1000 definitions')
    return jobs
