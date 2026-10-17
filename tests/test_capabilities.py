from threading import Event

from media_wrapper.infrastructure.ffmpeg.capabilities import discover_build, parse_hwaccels


def test_build_cache_and_binary_identity(tmp_path, monkeypatch):
    executable = tmp_path/'ffmpeg'
    executable.write_bytes(b'build1')
    calls = []
    def read(binary, args, event):
        calls.append(tuple(args))
        if args == ['-encoders']:
            return ' V....D libx264 H264\n V....D h264_nvenc NVIDIA'
        if args == ['-hwaccels']:
            return 'Hardware acceleration methods:\ncuda\nvaapi\n'
        return 'build details'
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.capabilities.read_binary', read)
    first = discover_build(executable, Event())
    calls.clear()
    assert discover_build(executable, Event()) is first
    assert calls == [('-version',)]
    assert first.hwaccels == ('cuda', 'vaapi')
    assert len(first.encoder_help) == 2
    executable.write_bytes(b'build two changed')
    assert discover_build(executable, Event()).identity != first.identity
    assert discover_build(executable, Event(), refresh=True) is not first


def test_hwaccel_parser():
    assert parse_hwaccels('Hardware acceleration methods:\ncuda\nvaapi\n\n') == ('cuda', 'vaapi')


def test_listed_is_never_runtime_proof(monkeypatch):
    from pathlib import Path

    from media_wrapper.application.capability_service import scan_capabilities
    from media_wrapper.domain.capabilities import BuildCapabilities, EncoderStatus
    build = BuildCapabilities(('test', 1, 1, 'version'), 'version', '', frozenset({'h264_nvenc'}), ('cuda',), ())
    monkeypatch.setattr('media_wrapper.application.capability_service.discover_build', lambda *a, **k: build)
    report = scan_capabilities(Path('ffmpeg'), Event())
    assert not report.working()
    assert report.gpu[0].status == EncoderStatus.LISTED
    assert any(c.status == EncoderStatus.UNAVAILABLE for c in report.gpu)


def test_gpu_smoke_reports_failure_success_and_missing_device(monkeypatch):
    import subprocess
    from pathlib import Path

    from media_wrapper.domain.capabilities import EncoderStatus
    from media_wrapper.infrastructure.ffmpeg.gpu_probe import gpu_probe_command, test_gpu_encoder
    command = gpu_probe_command(Path('ffmpeg'), 'h264_vaapi', '/dev/dri/renderD129')
    assert 'format=nv12,hwupload' in command and command[-1] == '-'
    assert test_gpu_encoder(Path('ffmpeg'), 'h264_vaapi', Event()).status == EncoderStatus.UNKNOWN
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.gpu_probe.run_cancellable_probe',
                        lambda *a, **k: subprocess.CompletedProcess([], 1, '', 'driver unavailable'))
    failed = test_gpu_encoder(Path('ffmpeg'), 'h264_nvenc', Event())
    assert failed.status == EncoderStatus.UNAVAILABLE and 'driver unavailable' in failed.detail
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.gpu_probe.run_cancellable_probe',
                        lambda *a, **k: subprocess.CompletedProcess([], 0, '', ''))
    assert test_gpu_encoder(Path('ffmpeg'), 'h264_nvenc', Event()).status == EncoderStatus.WORKING


def test_gpu_probe_cancellation_is_not_a_failure(monkeypatch):
    from pathlib import Path

    import pytest

    from media_wrapper.domain.inspection import OperationCancelled
    from media_wrapper.infrastructure.ffmpeg.gpu_probe import test_gpu_encoder
    def cancel(*a, **k):
        raise OperationCancelled()
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.gpu_probe.run_cancellable_probe', cancel)
    with pytest.raises(OperationCancelled):
        test_gpu_encoder(Path('ffmpeg'), 'h264_nvenc', Event())
