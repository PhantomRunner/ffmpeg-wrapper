"""Portable workflow presets with rules that resolve against each source."""
import json
import re
from collections import Counter
from dataclasses import dataclass, fields, replace
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.draft import MIXED
from media_wrapper.domain.operation_policy import ENCODERS
from media_wrapper.domain.operations import EncodingProfile, MediaOperation
from media_wrapper.domain.profile_document import parse_profile, profile_payload
from media_wrapper.domain.remux import Container

SETTINGS = ('container', 'width', 'height', 'fps', 'audio_bitrate', 'mode', 'crf',
            'video_bitrate', 'preset', 'audio_quality', 'target_size_bytes', 'hardware_mode',
            'gpu_encoder', 'metadata_policy', 'chapter_policy', 'custom_arguments')
REMUX_SETTINGS = ('container', 'metadata_policy', 'chapter_policy')
OPTIONAL_SETTINGS = ('codec_profile', 'pixel_format', 'target_size', 'deep_verify')
STREAM_KINDS = {'video', 'audio', 'subtitle', 'attachment', 'data', 'unknown'}


@dataclass(frozen=True)
class TrackRule:
    kind: str
    action: str
    ordinal: int
    title: str = ''
    language: str = ''
    profile: EncodingProfile | None = None


@dataclass(frozen=True)
class NamedPreset:
    name: str
    operation: MediaOperation
    settings: tuple[tuple[str, object], ...]
    streams: tuple[tuple[str, str], ...]
    category: str = 'Custom'
    description: str = ''
    favorite: bool = False
    default: bool = False
    extraction: str = ''
    variant: str = ''
    track_rules: tuple[TrackRule, ...] = ()


def _profile_template():
    return ConversionRequest(Path('preset-placeholder.mkv'), Container.MATROSKA, ())


def _rules_payload(rules):
    result = []
    for rule in rules:
        entry = {'kind': rule.kind, 'action': rule.action, 'ordinal': rule.ordinal,
                 'title': rule.title, 'language': rule.language}
        if rule.profile is not None:
            entry['profile'] = profile_payload(replace(_profile_template(), stream_profiles=((0, rule.profile),)))[
                'settings']['stream_profiles'][0][1]
        result.append(entry)
    return result


def preset_payload(preset):
    return {'name': preset.name, 'operation': preset.operation.value,
            'settings': dict(preset.settings), 'streams': dict(preset.streams),
            'category': preset.category, 'description': preset.description,
            'favorite': preset.favorite, 'default': preset.default,
            'extraction': preset.extraction, 'variant': preset.variant,
            'track_rules': _rules_payload(preset.track_rules)}


def _validate_action(kind, action, operation):
    if kind not in STREAM_KINDS:
        raise ValueError('Unsupported preset stream kind')
    if action not in ('copy', 'omit') and (action not in ENCODERS or ENCODERS[action][0] != kind):
        raise ValueError('Unsupported preset stream encoder')
    if operation == MediaOperation.REMUX and action not in ('copy', 'omit'):
        raise ValueError('Remux presets must use stream copy or omit')


def _parse_rules(entries, operation):
    if not isinstance(entries, list) or len(entries) > 256:
        raise ValueError('Invalid preset stream rules')
    rules = []
    for rule in entries:
        keys = {'kind', 'action', 'ordinal', 'title', 'language'}
        if not isinstance(rule, dict) or not keys <= rule.keys() <= keys | {'profile'}:
            raise ValueError('Invalid preset stream rule')
        kind, action, ordinal, title, language = (rule[k] for k in ('kind', 'action', 'ordinal', 'title', 'language'))
        if (not all(isinstance(value, str) for value in (kind, action, title, language))
                or type(ordinal) is not int or not 0 <= ordinal < 256):
            raise ValueError('Invalid preset stream selector')
        _validate_action(kind, action, operation)
        profile = None
        if 'profile' in rule:
            if action in ('copy', 'omit'):
                raise ValueError('Only converted tracks can have encoder settings')
            base = profile_payload(_profile_template())
            base['settings'].update(tracks=[[0, action]], stream_profiles=[[0, rule['profile']]])
            profile = dict(parse_profile(base, _profile_template().destination).stream_profiles)[0]
            if profile.encoder != action:
                raise ValueError('The preset stream encoder does not match its settings')
        rules.append(TrackRule(kind, action, ordinal, title, language, profile))
    if len({(r.kind, r.ordinal, r.title, r.language) for r in rules}) != len(rules):
        raise ValueError('Duplicate preset stream selector')
    return tuple(rules)


def parse_named_preset(data):
    required = {'name', 'operation', 'settings', 'streams'}
    optional = {'category', 'description', 'favorite', 'default', 'extraction', 'variant', 'track_rules'}
    if not isinstance(data, dict) or not required <= data.keys() <= required | optional:
        raise ValueError('Missing or unknown named preset fields')
    name = data['name']
    if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(c) < 32 for c in name):
        raise ValueError('Use a preset name of 1–120 characters without control characters')
    operation = MediaOperation(data['operation'])
    supported = {f.name for f in fields(ConversionRequest)}
    keys = tuple(key for key in (REMUX_SETTINGS + ('deep_verify',) if operation == MediaOperation.REMUX
                else SETTINGS + OPTIONAL_SETTINGS) if key in supported)
    if not isinstance(data['settings'], dict) or not data['settings'].keys() <= set(keys):
        raise ValueError('Invalid named preset settings')
    template = _profile_template()
    base = profile_payload(template)
    base['settings'].update(data['settings'])
    if isinstance(base['settings'].get('target_size'), tuple):
        base['settings']['target_size'] = list(base['settings']['target_size'])
    base['settings']['operation'] = (MediaOperation.CONVERT if operation == MediaOperation.REMUX else operation).value
    request = parse_profile(base, template.destination)
    streams = data['streams']
    if not isinstance(streams, dict):
        raise ValueError('Invalid preset stream policies')  # noqa: TRY004 - invalid serialized document
    for kind, action in streams.items():
        if not isinstance(action, str):
            raise ValueError('Invalid preset stream encoder')  # noqa: TRY004 - public document validation error
        _validate_action(kind, action, operation)
    category = data.get('category', 'Custom')
    description = data.get('description', '')
    favorite, default = data.get('favorite', False), data.get('default', False)
    extraction, variant = data.get('extraction', ''), data.get('variant', '')
    if (not isinstance(category, str) or not category.strip() or len(category) > 80
            or not isinstance(description, str) or len(description) > 500
            or type(favorite) is not bool or type(default) is not bool
            or extraction not in ('', 'selected', 'all')
            or variant not in ('', 'resolve-windows', 'extract-copy')
            or (variant == 'extract-copy' and not extraction)
            or (extraction and operation != MediaOperation.CONVERT)):
        raise ValueError('Invalid preset organization or workflow')
    return NamedPreset(name.strip(), operation, tuple((key, getattr(request, key)) for key in keys),
                       tuple(streams.items()), category.strip(), description, favorite, default,
                       extraction, variant, _parse_rules(data.get('track_rules', []), operation))


def capture_preset(draft, name, category='Custom'):
    if draft.multiple_outputs:
        return _capture_outputs(draft, name, category)
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
    return parse_named_preset({'name': name, 'operation': draft.operation.value, 'settings': values,
                               'streams': policies, 'category': category})


def _capture_outputs(draft, name, category):
    targets = draft.editable_outputs()
    if not targets:
        raise ValueError('Choose an inspected output first.')
    operation = targets[0].operation
    if any(output.operation != operation for output in targets):
        raise ValueError('Choose outputs with the same operation before saving a preset.')
    keys = REMUX_SETTINGS + ('deep_verify',) if operation == MediaOperation.REMUX else SETTINGS + OPTIONAL_SETTINGS
    request = targets[0].options[operation].request
    values = {key: draft.value(key) for key in keys if hasattr(request, key)}
    if any(value is MIXED for value in values.values()):
        raise ValueError('This scope has mixed settings. Select one output before saving.')
    rule_sets = []
    for output in targets:
        media = draft.items[output.source_id].media
        request = output.options[operation].request
        tracks = dict(request.tracks)
        profiles = dict(getattr(request, 'stream_profiles', ()))
        ordinals = Counter()
        rules = []
        for stream in media.streams:
            if stream.index is None:
                continue
            ordinal = ordinals[stream.kind]
            ordinals[stream.kind] += 1
            rules.append(TrackRule(stream.kind, tracks.get(stream.index, 'omit'), ordinal,
                                   stream.title or '', stream.language or '', profiles.get(stream.index)))
        rule_sets.append(tuple(rules))
    if any(rules != rule_sets[0] for rules in rule_sets[1:]):
        raise ValueError('Stream settings differ in this scope. Select one output before saving.')
    return parse_named_preset({'name': name, 'operation': operation.value, 'category': category,
                               'settings': values, 'streams': {}, 'track_rules': _rules_payload(rule_sets[0])})


def _resolve_track_rules(media, preset):
    streams = tuple(stream for stream in media.streams if stream.index is not None)
    policies = dict(preset.streams)
    tracks = {stream.index: policies.get(stream.kind, 'copy') for stream in streams}
    profiles, matched = {}, set()
    for rule in preset.track_rules:
        candidates = [stream for stream in streams if stream.kind == rule.kind]
        if rule.title:
            candidates = [stream for stream in candidates if stream.title == rule.title
                          and (not rule.language or stream.language == rule.language)]
        else:
            candidates = candidates[rule.ordinal:rule.ordinal + 1]
        if len(candidates) != 1 or candidates[0].index in matched:
            detail = rule.title or f'{rule.kind} {rule.ordinal + 1}'
            raise ValueError(f'{media.path.name}: cannot match preset track {detail!r}.')
        index = candidates[0].index
        matched.add(index)
        tracks[index] = rule.action
        if rule.profile is not None:
            profiles[index] = rule.profile
    if preset.variant == 'resolve-windows':
        for stream in streams:
            if (stream.kind == 'video' and stream.codec == 'h264' and stream.pixel_format == 'yuv420p'
                    and stream.profile in {'Baseline', 'Constrained Baseline', 'Main', 'High'}):
                tracks[stream.index] = 'copy'
    return tuple(tracks.items()), tuple(profiles.items())


def _extraction_jobs(media, preset, selected_streams):
    audio = tuple(s for s in media.streams if s.kind == 'audio' and s.index is not None)
    if (preset.extraction == 'selected'
            and (not selected_streams or not set(selected_streams) <= {stream.index for stream in audio})):
        raise ValueError(f'{media.path.name}: explicitly select the audio tracks to extract.')
    jobs = []
    for ordinal, stream in enumerate(audio, 1):
        if preset.extraction == 'selected' and stream.index not in selected_streams:
            continue
        title = stream.title or f'Audio {ordinal}'
        suffix = re.sub(r'[^\w -]+', '_', title, flags=re.UNICODE).strip(' _')[:48] or 'audio'
        encoder = dict(preset.streams).get('audio', 'copy')
        tracks = tuple((s.index, encoder if s.index == stream.index else 'omit')
                       for s in media.streams if s.index is not None)
        container = None
        if preset.variant == 'extract-copy':
            from media_wrapper.domain.containers import CONTAINERS
            order = (Container.WAV, Container.FLAC, Container.M4A, Container.MP3, Container.OPUS,
                     Container.MATROSKA)
            container = next((choice for choice in order if stream.codec in CONTAINERS[choice].codecs['audio']), None)
            if container is None:
                raise ValueError(f'{media.path.name}: choose a conversion format for {title} ({stream.codec}).')
        jobs.append((tracks, (), title, f'{{name}}_audio_{ordinal}_{suffix}', container))
    if not jobs:
        raise ValueError(f'{media.path.name}: no audio tracks to extract.')
    return jobs


def _apply_outputs(draft, preset, ids, selected_streams):
    outputs = draft._configurations(ids)
    if not outputs:
        raise ValueError('Choose an inspected output first.')
    if preset.extraction == 'selected' and len({output.source_id for output in outputs}) != 1:
        raise ValueError('Select audio tracks from a single source at a time.')
    prepared = []
    for output in outputs:
        media = draft.items[output.source_id].media
        if preset.extraction:
            jobs = _extraction_jobs(media, preset, selected_streams)
        else:
            tracks, profiles = _resolve_track_rules(media, preset)
            jobs = [(tracks, profiles, preset.name, None, None)]
        prepared.append((output, jobs))
    created = []
    for output, jobs in prepared:
        current = output.options[output.operation]
        for number, (tracks, profiles, label, template, container) in enumerate(jobs):
            target = draft.add_output(output.source_id, label, preset.operation) if number else output
            options = target.defaults[preset.operation]
            settings = dict(preset.settings)
            if container is not None:
                settings['container'] = container
            if hasattr(options.request, 'stream_profiles'):
                settings['stream_profiles'] = profiles
            request = replace(options.request, tracks=tracks, **settings)
            target.operation, target.label = preset.operation, label
            target.options[preset.operation] = replace(
                options, request=request, preset_name=preset.name, folder=current.folder,
                template=template or current.template, auto_number=current.auto_number,
                output_override='' if template else current.output_override,
            )
            target.revision += 1
            draft.revision += 1
            created.append(target)
    if draft.active_output_id is not None:
        draft.focus_output(draft.active_output_id)
    return tuple(created)


def apply_named_preset(draft, preset, ids=None, *, selected_streams=()):
    if draft.multiple_outputs:
        return _apply_outputs(draft, preset, ids, selected_streams)
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
            or payload['kind'] != 'media-wrapper-presets' or type(payload['version']) is not int or payload['version'] not in (1, 2)
            or not isinstance(payload['presets'], list) or len(payload['presets']) > 1000):
        raise ValueError('Unsupported named preset schema/version; the original file is preserved')
    presets = tuple(parse_named_preset(entry) for entry in payload['presets'])
    if len({p.name for p in presets}) != len(presets):
        raise ValueError('Duplicate named presets')
    return {preset.name: preset for preset in presets}


@lru_cache(maxsize=1)
def _factory_presets():
    resource = files('media_wrapper').joinpath('resources', 'workflow-presets.json')
    return tuple(named_presets_document(json.loads(resource.read_text(encoding='utf-8'))).items())


def factory_presets():
    return dict(_factory_presets())
