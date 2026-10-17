from threading import Event

from media_wrapper.infrastructure.ffmpeg.capabilities import (
    discover_build,
    parse_hwaccels,
)


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
    from media_wrapper.infrastructure.ffmpeg.gpu_probe import (
        gpu_probe_command,
        test_gpu_encoder,
    )
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


def test_cpu_gpu_auto_selection_requires_runtime_evidence(sample):
    from dataclasses import replace

    import pytest

    from media_wrapper.application.hardware_selection import select_hardware
    from media_wrapper.domain.capabilities import (
        BuildCapabilities,
        CapabilityReport,
        EncoderCapability,
        EncoderStatus,
    )
    from media_wrapper.domain.media import MediaStream
    from media_wrapper.domain.operations import (
        EncodingProfile,
        MediaOperation,
        StreamSelection,
    )
    _, plan = sample
    plan = replace(plan, operation=MediaOperation.CONVERT,
                   media=replace(plan.media, streams=(MediaStream(0, 'video', 'h264'),)),
                   streams=(StreamSelection(0, EncodingProfile('libx264', bitrate=1000000)),))
    build = BuildCapabilities(('test', 1, 1, 'v'), 'v', '', frozenset({'libx264','h264_nvenc'}), (), ())
    report = CapabilityReport(build, (EncoderCapability('h264_nvenc', True, EncoderStatus.LISTED),))
    assert select_hardware(plan, report, 'Auto').streams[0].profile.encoder == 'libx264'
    with pytest.raises(ValueError, match='runtime-tested'):
        select_hardware(plan, report, 'GPU')
    report = replace(report, gpu=(EncoderCapability('h264_nvenc', True, EncoderStatus.WORKING),))
    selected = select_hardware(plan, report, 'Auto')
    assert selected.streams[0].profile.encoder == 'h264_nvenc'
    assert 'h264_nvenc' in selected.hardware_note
    assert select_hardware(plan, report, 'CPU') is plan
    quality = replace(plan, streams=(StreamSelection(0, EncodingProfile('libx264', crf=23)),))
    assert select_hardware(quality, report, 'Auto').streams[0].profile.encoder == 'libx264'


def test_vaapi_command_has_explicit_device_and_upload(sample):
    from dataclasses import replace

    from media_wrapper.domain.media import MediaStream
    from media_wrapper.domain.operations import (
        EncodingProfile,
        MediaOperation,
        StreamSelection,
    )
    from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder
    binaries, plan = sample
    plan = replace(plan, operation=MediaOperation.CONVERT, hardware_device='/dev/dri/renderD129',
                   media=replace(plan.media, streams=(MediaStream(0, 'video', 'h264'),)),
                   streams=(StreamSelection(0, EncodingProfile('h264_vaapi', bitrate=1000000, width=64, height=48)),))
    command = CommandBuilder().build(binaries.ffmpeg, plan, frozenset({'h264_vaapi'}))
    assert command[command.index('-vaapi_device')+1] == '/dev/dri/renderD129'
    assert 'scale=64:48,format=nv12,hwupload' in command


def test_failed_gpu_job_requires_explicit_cpu_retry(video_sample, monkeypatch):
    from dataclasses import replace

    from PySide6.QtWidgets import QApplication
    from test_operation_task import wait

    from media_wrapper.application.conversion_service import (
        ConversionRequest,
        conversion_plan,
    )
    from media_wrapper.application.task_queue import TaskQueue
    from media_wrapper.domain.capabilities import EncoderCapability, EncoderStatus
    from media_wrapper.domain.tasks import TaskStatus
    from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders
    app = QApplication.instance() or QApplication([])
    binaries, base = video_sample
    real_encoders = list_encoders(binaries.ffmpeg, Event())
    if 'libx264' not in real_encoders:
        import pytest
        pytest.skip('CPU retry requires libx264')
    plan = conversion_plan(base.media, ConversionRequest(base.output.path, base.output.container, ((0, 'libx264'),)))
    selected = plan.streams[0]
    plan = replace(plan, streams=(replace(selected, profile=replace(selected.profile, encoder='h264_nvenc')),))
    monkeypatch.setattr('media_wrapper.application.operation_task.list_encoders', lambda *a: real_encoders | {'h264_nvenc'})
    monkeypatch.setattr('media_wrapper.application.operation_task.test_gpu_encoder',
                        lambda *a: EncoderCapability('h264_nvenc', True, EncoderStatus.UNAVAILABLE, 'driver initialization failed'))
    queue = TaskQueue()
    failed = queue.add(plan, binaries)
    queue.start()
    wait(app, lambda: not queue.running)
    assert failed.status == TaskStatus.FAILED and not base.output.path.exists()
    assert len(queue.records) == 1 and 'driver initialization failed' in failed.log
    cpu = queue.retry_cpu(failed.id)
    assert cpu.id != failed.id and cpu.plan.streams[0].profile.encoder == 'libx264'
    queue.start()
    wait(app, lambda: not queue.running)
    assert cpu.status == TaskStatus.COMPLETED, cpu.error
    assert failed.status == TaskStatus.FAILED and failed.log


def test_multiple_gpu_preference_and_unknown_state(sample):
    from dataclasses import replace

    from media_wrapper.application.hardware_selection import select_hardware
    from media_wrapper.domain.capabilities import (
        BuildCapabilities,
        CapabilityReport,
        EncoderCapability,
        EncoderStatus,
    )
    from media_wrapper.domain.media import MediaStream
    from media_wrapper.domain.operations import (
        EncodingProfile,
        MediaOperation,
        StreamSelection,
    )
    _, plan = sample
    plan = replace(plan, operation=MediaOperation.CONVERT,
                   media=replace(plan.media, streams=(MediaStream(0, 'video', 'h264'),)),
                   streams=(StreamSelection(0, EncodingProfile('libx264')),))
    build = BuildCapabilities(('x', 1, 1, 'v'), 'v', '', frozenset(), (), ())
    report = CapabilityReport(build, (EncoderCapability('h264_nvenc', True, EncoderStatus.WORKING),
                                     EncoderCapability('h264_qsv', True, EncoderStatus.WORKING),
                                     EncoderCapability('h264_vaapi', True, EncoderStatus.UNKNOWN)))
    assert select_hardware(plan, report, 'Auto').streams[0].profile.encoder == 'h264_nvenc'
    assert select_hardware(plan, report, 'GPU', 'h264_qsv').streams[0].profile.encoder == 'h264_qsv'
    assert 'h264_vaapi' not in report.working()


def test_gpu_timeout_reports_unavailable(monkeypatch):
    import subprocess
    from pathlib import Path

    from media_wrapper.domain.capabilities import EncoderStatus
    from media_wrapper.infrastructure.ffmpeg.gpu_probe import test_gpu_encoder
    def timeout(*a, **k):
        raise subprocess.TimeoutExpired('ffmpeg', 15)
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.gpu_probe.run_cancellable_probe', timeout)
    result = test_gpu_encoder(Path('ffmpeg'), 'h264_qsv', Event())
    assert result.status == EncoderStatus.UNAVAILABLE and '15' in result.detail


def test_cpu_retry_retains_existing_partial(sample):
    from dataclasses import replace

    from media_wrapper.application.task_queue import TaskQueue
    from media_wrapper.domain.media import MediaStream
    from media_wrapper.domain.operations import (
        EncodingProfile,
        MediaOperation,
        StreamSelection,
    )
    from media_wrapper.domain.tasks import TaskStatus
    binaries, plan = sample
    plan = replace(plan, operation=MediaOperation.CONVERT,
                   media=replace(plan.media, streams=(MediaStream(0, 'video', 'h264'),)),
                   streams=(StreamSelection(0, EncodingProfile('h264_nvenc', bitrate=1000000)),))
    queue = TaskQueue()
    failed = queue.add(plan, binaries)
    failed.transition(TaskStatus.PREPARING)
    failed.transition(TaskStatus.RUNNING)
    failed.transition(TaskStatus.FAILED)
    failed.partial_path = plan.output.path.with_name('original.partial.mkv')
    failed.partial_path.write_bytes(b'failed GPU attempt')
    failed.log = 'original diagnostics'
    retried = queue.retry_cpu(failed.id)
    assert failed.partial_path.read_bytes() == b'failed GPU attempt'
    assert failed.log == 'original diagnostics'
    assert retried.plan.output.temporary_path is None and retried.id != failed.id
