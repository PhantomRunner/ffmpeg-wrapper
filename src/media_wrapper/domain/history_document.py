"""Strict terminal-attempt snapshots. Reading never probes media or resumes work."""
import math
from dataclasses import asdict, fields
from fractions import Fraction
from pathlib import Path

from media_wrapper.domain.media import MediaChapter, MediaFile, MediaStream
from media_wrapper.domain.queue_document import parse_definition, plan_payload
from media_wrapper.domain.tasks import TaskRecord, TaskStatus

TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


def media_payload(media):
    if media is None:
        return None
    data = asdict(media)
    data['path'] = str(media.path)
    data['streams'] = list(data['streams'])
    data['tags'] = [list(tag) for tag in data['tags']]
    data['chapters'] = list(data['chapters'])
    for stream in data['streams']:
        for name in ('average_frame_rate', 'nominal_frame_rate'):
            stream[name] = str(stream[name]) if stream[name] is not None else None
    return data


def _text(value, maximum=32768, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
        raise ValueError('Invalid history text')
    return value


def _number(value, integer=False):
    if value is None:
        return None
    if (type(value) not in (int, float) or not math.isfinite(value) or value < 0
            or integer and type(value) is not int):
        raise ValueError('Invalid history numeric value')
    return value


def parse_media(data):
    if data is None:
        return None
    if not isinstance(data, dict) or set(data) != {f.name for f in fields(MediaFile)}:
        raise ValueError('Invalid history media fields')
    if not isinstance(data['streams'], list) or len(data['streams']) > 256:
        raise ValueError('Invalid history streams')
    streams = []
    for value in data['streams']:
        if not isinstance(value, dict) or set(value) != {f.name for f in fields(MediaStream)}:
            raise ValueError('Invalid history stream fields')
        stream = dict(value)
        for name in ('index', 'bit_rate', 'width', 'height', 'sample_rate', 'channels'):
            stream[name] = _number(stream[name], True)
        for name in ('kind', 'codec'):
            stream[name] = _text(stream[name])
        for name in ('codec_long_name', 'language', 'title', 'channel_layout', 'codec_tag'):
            stream[name] = _text(stream[name], optional=True)
        for name in ('average_frame_rate', 'nominal_frame_rate'):
            rate = stream[name]
            stream[name] = Fraction(_text(rate, 64)) if rate is not None else None
        streams.append(MediaStream(**stream))
    tags = data['tags']
    if not isinstance(tags, list) or len(tags) > 1024 or any(not isinstance(t, list) or len(t) != 2 for t in tags):
        raise ValueError('Invalid history tags')
    if not isinstance(data['chapters'], list) or len(data['chapters']) > 10000:
        raise ValueError('Invalid history chapters')
    chapters = []
    for chapter in data['chapters']:
        if not isinstance(chapter, dict) or set(chapter) != {'start', 'end', 'title'}:
            raise ValueError('Invalid history chapter')
        chapters.append(MediaChapter(_number(chapter['start']), _number(chapter['end']), _text(chapter['title'], optional=True)))
    return MediaFile(Path(_text(data['path'])), _text(data['format_name']), _number(data['duration']),
                     _number(data['size_bytes'], True), tuple(streams), _number(data['bit_rate'], True),
                     tuple((_text(k), _text(v)) for k, v in tags), tuple(chapters))


def record_payload(record):
    if record.status not in TERMINAL:
        raise ValueError('Only terminal attempts belong to history')
    return {
        'id': record.id, 'status': record.status.value,
        'intent': plan_payload(record.plan, record.source_fingerprint or (0, 0)),
        'media': media_payload(record.plan.media), 'result': media_payload(record.result),
        'commands': [list(command) for command in record.commands or ((record.command,) if record.command else ())],
        'log': record.log[-16000:], 'error': record.error[-16000:], 'failure_detail': record.failure_detail[-16000:],
        'partial_path': str(record.partial_path) if record.partial_path else None,
        'created_at': record.created_at, 'started_at': record.started_at, 'finished_at': record.finished_at,
        'elapsed_seconds': record.elapsed_seconds, 'pass_index': record.pass_index, 'pass_count': record.pass_count,
        'source_fingerprint': list(record.source_fingerprint) if record.source_fingerprint else None,
        'binary_version': record.binary_version,
    }


KEYS = {'id', 'status', 'intent', 'media', 'result', 'commands', 'log', 'error', 'failure_detail',
        'partial_path', 'created_at', 'started_at', 'finished_at', 'elapsed_seconds', 'pass_index',
        'pass_count', 'source_fingerprint', 'binary_version'}


def parse_record(data):
    if not isinstance(data, dict) or set(data) != KEYS:
        raise ValueError('Missing or unknown history record fields')
    status = TaskStatus(data['status'])
    if status not in TERMINAL:
        raise ValueError('History cannot contain active or pending jobs')
    media = parse_media(data['media'])
    if media is None:
        raise ValueError('History needs the frozen source metadata')
    plan = parse_definition(data['intent'], media)
    if str(media.path) != data['intent']['source']:
        raise ValueError('History source metadata does not match its saved intent')
    commands = data['commands']
    if (not isinstance(commands, list) or len(commands) > 16
            or any(not isinstance(c, list) or len(c) > 4096 for c in commands)):
        raise ValueError('Invalid history commands')
    commands = tuple(tuple(_text(arg) for arg in command) for command in commands)
    fingerprint = data['source_fingerprint']
    if fingerprint is not None:
        if not isinstance(fingerprint, list) or len(fingerprint) != 2 or any(type(v) is not int for v in fingerprint) or fingerprint[0] < 0:
            raise ValueError('Invalid history source fingerprint')
        fingerprint = tuple(fingerprint)
    if any(type(data[n]) is not int or not 0 <= data[n] <= 16 for n in ('pass_index', 'pass_count')):
        raise ValueError('Invalid history pass information')
    return TaskRecord(plan, id=_text(data['id'], 128), status=status, command=commands[-1] if commands else (),
                      commands=commands, log=_text(data['log'], 16000), error=_text(data['error'], 16000),
                      failure_detail=_text(data['failure_detail'], 16000),
                      partial_path=Path(_text(data['partial_path'])) if data['partial_path'] else None,
                      result=parse_media(data['result']), created_at=_text(data['created_at'], 128),
                      started_at=_text(data['started_at'], 128, True), finished_at=_text(data['finished_at'], 128, True),
                      elapsed_seconds=_number(data['elapsed_seconds']), pass_index=data['pass_index'],
                      pass_count=data['pass_count'], source_fingerprint=fingerprint,
                      binary_version=_text(data['binary_version']))


def history_entries(payload):
    if (not isinstance(payload, dict) or set(payload) != {'kind', 'version', 'records'}
            or payload['kind'] != 'media-wrapper-history' or type(payload['version']) is not int or payload['version'] != 1
            or not isinstance(payload['records'], list)):
        raise ValueError('Unsupported history schema/version; the original file is preserved')
    records = tuple(parse_record(entry) for entry in payload['records'])
    if len({record.id for record in records}) != len(records):
        raise ValueError('Duplicate history attempt IDs')
    return records
