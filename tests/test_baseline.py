"""Binary/probe baseline contracts, using fake process results for error cases."""
import json
import subprocess
from pathlib import Path

import pytest

from media_wrapper.domain.media import MediaInfo
from media_wrapper.infrastructure.ffmpeg import binary_resolver as resolver
from media_wrapper.infrastructure.ffmpeg.probe_service import inspect_media


@pytest.mark.parametrize('mode', ['external', 'bundled'])
def test_explicit_binary_folder_and_no_path_fallback(tmp_path, monkeypatch, mode):
    folder = tmp_path/'bin ü space'
    folder.mkdir()
    for name in ('ffmpeg', 'ffprobe'):
        (folder/resolver._program(name)).touch()
    monkeypatch.setattr(resolver.shutil, 'which', lambda _: pytest.fail('Unexpected PATH fallback'))
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, 'version test\n', '')
    monkeypatch.setattr(resolver.subprocess, 'run', run)
    result = resolver.resolve(mode, folder)
    assert result.ffmpeg == (folder/resolver._program('ffmpeg')).resolve()
    assert len(calls) == 2
    assert all(args[1:] == ['-version'] and options['timeout'] == 8
               and options.get('shell', False) is False for args, options in calls)
    result.ffprobe.unlink()
    with pytest.raises(FileNotFoundError):
        resolver.resolve(mode, folder)


def test_path_resolution_and_missing_binary(tmp_path, monkeypatch):
    binary = tmp_path/'binary'
    binary.touch()
    monkeypatch.setattr(resolver.shutil, 'which', lambda _: str(binary))
    monkeypatch.setattr(resolver.subprocess, 'run', lambda args, **kw: subprocess.CompletedProcess(args, 0, 'ok', ''))
    assert resolver.resolve().ffmpeg == binary.resolve()
    monkeypatch.setattr(resolver.shutil, 'which', lambda _: None)
    with pytest.raises(FileNotFoundError, match='PATH'):
        resolver.resolve()


@pytest.mark.parametrize('error', [PermissionError('denied'), subprocess.TimeoutExpired('ffmpeg', 8),
                                   subprocess.CalledProcessError(1, 'ffmpeg')])
def test_binary_execution_failures_are_causal(tmp_path, monkeypatch, error):
    for name in ('ffmpeg', 'ffprobe'):
        (tmp_path/resolver._program(name)).touch()
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(resolver.subprocess, 'run', fail)
    with pytest.raises(RuntimeError) as raised:
        resolver.resolve(directory=tmp_path)
    assert raised.value.__cause__ is error


@pytest.mark.parametrize(('platform', 'expected'), [('win32', 'ffmpeg.exe'), ('linux', 'ffmpeg')])
def test_executable_suffix(monkeypatch, platform, expected):
    monkeypatch.setattr(resolver.sys, 'platform', platform)
    assert resolver._program('ffmpeg') == expected


def test_probe_paths_are_absolute_single_arguments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = Path('-clip ü.wav')
    source.touch()
    def run(args, **kwargs):
        assert args[-1] == str(source.absolute())
        assert kwargs.get('shell', False) is False
        assert kwargs['timeout'] == 30
        return subprocess.CompletedProcess(args, 0, json.dumps({'streams': [{'index': 2}]}), '')
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.probe_service.subprocess.run', run)
    assert inspect_media(Path('ffprobe'), source).streams[0]['index'] == 2


@pytest.mark.parametrize(('stdout', 'stderr', 'code', 'exception'), [
    ('{', '', 0, ValueError), ('[]', '', 0, ValueError),
    ('{}', 'Invalid media', 1, RuntimeError), ('{}', '', 3, RuntimeError),
    ('{"streams": [null]}', '', 0, ValueError), ('{"format": []}', '', 0, ValueError),
])
def test_bad_probe_output(tmp_path, monkeypatch, stdout, stderr, code, exception):
    source = tmp_path/'input'
    source.touch()
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.probe_service.subprocess.run',
                        lambda args, **kw: subprocess.CompletedProcess(args, code, stdout, stderr))
    with pytest.raises(exception):
        inspect_media(Path('ffprobe'), source)


def test_missing_source_does_not_launch_process(tmp_path, monkeypatch):
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.probe_service.subprocess.run',
                        lambda *args, **kw: pytest.fail('Process launched for missing source'))
    with pytest.raises(FileNotFoundError):
        inspect_media(Path('ffprobe'), tmp_path/'missing')


@pytest.mark.parametrize('duration', ['NaN', 'Infinity', '-1', 'N/A', None])
def test_invalid_duration_is_unknown(duration):
    assert MediaInfo.from_probe(Path('input'), {'format': {'duration': duration}}).duration is None


@pytest.mark.parametrize('payload', [{'format': 2}, {'streams': {}}, {'streams': [1]}])
def test_invalid_probe_shape(payload):
    with pytest.raises(ValueError):
        MediaInfo.from_probe(Path('input'), payload)
