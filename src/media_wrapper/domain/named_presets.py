"""Portable named starting points: semantic stream policies, never source indices."""
from dataclasses import dataclass
from pathlib import Path

from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.draft import MIXED
from media_wrapper.domain.operation_policy import ENCODERS
from media_wrapper.domain.operations import MediaOperation
from media_wrapper.domain.profile_document import parse_profile, profile_payload
from media_wrapper.domain.remux import Container

SETTINGS = ('container', 'width', 'height', 'fps', 'audio_bitrate', 'mode', 'crf',
            'video_bitrate', 'preset', 'audio_quality', 'target_size_bytes', 'hardware_mode',
            'gpu_encoder', 'metadata_policy', 'chapter_policy', 'custom_arguments')
REMUX_SETTINGS = ('container', 'metadata_policy', 'chapter_policy')


@dataclass(frozen=True)
class NamedPreset:
    name: str
    operation: MediaOperation
    settings: tuple[tuple[str, object], ...]
    streams: tuple[tuple[str, str], ...]


def preset_payload(preset):
    return {'name': preset.name, 'operation': preset.operation.value,
            'settings': dict(preset.settings), 'streams': dict(preset.streams)}


def parse_named_preset(data):
    if not isinstance(data, dict) or set(data) != {'name', 'operation', 'settings', 'streams'}:
        raise ValueError('Missing or unknown named preset fields')
    name = data['name']
    if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(c) < 32 for c in name):
        raise ValueError('Use a preset name of 1–120 characters without control characters')
    operation = MediaOperation(data['operation'])
    keys = REMUX_SETTINGS if operation == MediaOperation.REMUX else SETTINGS
    if not isinstance(data['settings'], dict) or set(data['settings']) != set(keys):
        raise ValueError('Invalid named preset settings')
    # Reuse the established representable/allowlisted profile schema, even for
    # the smaller remux subset; no source or destination is stored in a preset.
    placeholder = Path('/preset-placeholder.mkv')
    base = profile_payload(ConversionRequest(placeholder, Container.MATROSKA, ()))
    base['settings'].update(data['settings'])
    base['settings']['operation'] = (MediaOperation.CONVERT if operation == MediaOperation.REMUX else operation).value
    request = parse_profile(base, placeholder)
    streams = data['streams']
    if not isinstance(streams, dict):
        raise ValueError('Invalid preset stream policies')  # noqa: TRY004 - invalid serialized document
    for kind, encoder in streams.items():
        if kind not in {'video', 'audio', 'subtitle', 'attachment', 'data', 'unknown'}:
            raise ValueError('Unsupported preset stream kind')
        if encoder not in ('copy', 'omit') and (encoder not in ENCODERS or ENCODERS[encoder][0] != kind):
            raise ValueError('Unsupported preset stream encoder')
        if operation == MediaOperation.REMUX and encoder not in ('copy', 'omit'):
            raise ValueError('Remux presets must use stream copy or omit')
    return NamedPreset(name.strip(), operation, tuple((key, getattr(request, key)) for key in keys),
                       tuple(streams.items()))


def capture_preset(draft, name):
    targets = draft.editable()
    if not targets:
        raise ValueError('Choose an inspected edit scope first')
    keys = REMUX_SETTINGS if draft.operation == MediaOperation.REMUX else SETTINGS
    values = {key: draft.value(key) for key in keys}
    if any(value is MIXED for value in values.values()):
        raise ValueError('This scope has mixed settings. Select one file or make the settings consistent before saving.')
    policies = {}
    for item in targets:
        choices = dict(item.options[draft.operation].request.tracks)
        for stream in item.media.streams:
            if stream.index is None:
                continue
            value = choices.get(stream.index, 'omit')
            if stream.kind in policies and policies[stream.kind] != value:
                raise ValueError('Stream actions differ within this scope. Export an exact per-file profile or select consistent stream actions.')
            policies[stream.kind] = value
    return parse_named_preset({'name': name, 'operation': draft.operation.value, 'settings': values, 'streams': policies})


def apply_named_preset(draft, preset):
    if draft.operation != preset.operation:
        raise ValueError('Switch to the preset operation first')
    for item in draft.editable():
        for name, value in preset.settings:
            draft.patch(name, value, (item.id,), preset_name=preset.name)
        policies = dict(preset.streams)
        current = dict(item.options[draft.operation].request.tracks)
        tracks = tuple((stream.index, policies.get(stream.kind, current.get(stream.index, 'omit')))
                       for stream in item.media.streams if stream.index is not None)
        draft.patch('tracks', tracks, (item.id,), preset_name=preset.name)


def named_presets_document(payload):
    if (not isinstance(payload, dict) or set(payload) != {'kind', 'version', 'presets'}
            or payload['kind'] != 'media-wrapper-presets' or type(payload['version']) is not int or payload['version'] != 1
            or not isinstance(payload['presets'], list) or len(payload['presets']) > 1000):
        raise ValueError('Unsupported named preset schema/version; the original file is preserved')
    presets = tuple(parse_named_preset(entry) for entry in payload['presets'])
    if len({p.name for p in presets}) != len(presets):
        raise ValueError('Duplicate named presets')
    return {preset.name: preset for preset in presets}
