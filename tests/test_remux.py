import subprocess
from pathlib import Path

import pytest

from media_wrapper.application.errors import ApplicationError
from media_wrapper.application.media_service import MediaService
from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.remux import Container, RemuxRequest, Stream
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries, resolve
from media_wrapper.infrastructure.ffmpeg.command_builder import build_remux_command


def test_command_preserves_paths_and_selection(tmp_path):
    source = tmp_path / 'source ü clip.mkv'
    destination = tmp_path / 'out clip.mp4'
    request = RemuxRequest(source, destination, Container.MP4,
                           (Stream(2, 'video', 'h264'), Stream(4, 'audio', 'aac')))
    assert build_remux_command(Path('ffmpeg'), request) == [
        'ffmpeg', '-hide_banner', '-nostdin', '-n', '-i', str(source),
        '-map', '0:2', '-map', '0:4', '-c', 'copy', '-f', 'mp4', str(destination)]


@pytest.mark.parametrize('streams', [(), (Stream(-1, 'audio', 'aac'),),
                                    (Stream(0, 'audio', 'aac'), Stream(0, 'audio', 'aac'))])
def test_invalid_selection(tmp_path, streams):
    with pytest.raises(ValueError):
        build_remux_command(Path('ffmpeg'), RemuxRequest(tmp_path/'a', tmp_path/'b', Container.MP4, streams))


@pytest.fixture
def service(tmp_path, monkeypatch):
    source = tmp_path / 'input.mkv'
    source.write_bytes(b'source')
    service = MediaService(Binaries(Path('ffmpeg'), Path('ffprobe'), 'test'))
    monkeypatch.setattr(service, 'inspect', lambda path: MediaFile(path, 'matroska', 1, 6,
                        (MediaStream(0, 'audio', 'aac'),)))
    return service, source


@pytest.mark.parametrize('case', ['same', 'existing', 'missing_parent', 'extension', 'missing_source'])
def test_invalid_paths(service, tmp_path, case):
    svc, source = service
    destination = tmp_path / 'output.mp4'
    if case == 'same':
        destination = source
    elif case == 'existing':
        destination.write_bytes(b'keep')
    elif case == 'missing_parent':
        destination = tmp_path/'missing'/'out.mp4'
    elif case == 'extension':
        destination = tmp_path/'out.wav'
    else:
        source = tmp_path/'missing.mkv'
    with pytest.raises(ApplicationError):
        svc.prepare_remux(source, destination, Container.MP4)
    if case == 'existing':
        assert destination.read_bytes() == b'keep'


def test_unsupported_stream_is_not_silently_dropped(service, tmp_path, monkeypatch):
    svc, source = service
    monkeypatch.setattr(svc, 'inspect', lambda path: MediaFile(path, 'mkv', None, None,
                        (MediaStream(0, 'attachment', 'ttf'),)))
    with pytest.raises(ApplicationError, match='Stream 0'):
        svc.prepare_remux(source, tmp_path/'out.mp4', Container.MP4)


def test_all_streams_are_mapped(service, tmp_path):
    svc, source = service
    command = svc.prepare_remux(source, tmp_path/'out.mp4', Container.MP4)
    assert command[command.index('-map') + 1] == '0:0'


def test_real_remux_and_overwrite_refusal(tmp_path):
    try:
        binaries = resolve()
    except (FileNotFoundError, RuntimeError) as exc:
        pytest.skip(str(exc))
    source, destination = tmp_path/'source clip.wav', tmp_path/'output clip.mkv'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i',
                    'sine=duration=0.1', '-c:a', 'pcm_s16le', '-n', str(source)],
                   check=True, capture_output=True, timeout=15)
    svc = MediaService(binaries)
    command = svc.prepare_remux(source, destination, Container.MATROSKA)
    subprocess.run(command, check=True, capture_output=True, timeout=15)
    assert svc.inspect(destination).streams[0].codec == 'pcm_s16le'
    before = destination.read_bytes()
    result = subprocess.run(command, capture_output=True, timeout=15, check=False)
    assert b'Exiting' in result.stderr or b'Not overwriting' in result.stderr or result.returncode != 0
    assert destination.read_bytes() == before


@pytest.mark.parametrize('index', [None, -1, '0', True])
def test_stream_parser_rejects_invalid_index(index):
    with pytest.raises(ValueError, match='index'):
        Stream.from_probe({'index': index})


def test_stream_parser_retains_index_and_missing_codec():
    assert Stream.from_probe({'index': 3}) == Stream(3, 'unknown', 'unknown')


def test_builder_rejects_source_as_destination(tmp_path):
    source = tmp_path/'source.mkv'
    with pytest.raises(ValueError, match='differ'):
        build_remux_command(Path('ffmpeg'), RemuxRequest(source, source, Container.MATROSKA,
                                                        (Stream(0, 'audio', 'aac'),)))
