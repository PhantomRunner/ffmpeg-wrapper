"""Batch failure isolation, cancellation semantics and child-process cleanup."""
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from media_wrapper.application.inspection_batch import InspectionBatch
from media_wrapper.application.media_service import MediaService
from media_wrapper.domain.inspection import InspectionStatus as Status
from media_wrapper.domain.inspection import OperationCancelled
from media_wrapper.domain.media import MediaFile
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.probe_service import run_cancellable_probe


def test_batch_preserves_success_and_continues_after_failure(monkeypatch, caplog):
    service = MediaService(Binaries(Path('ffmpeg'), Path('ffprobe'), 'test'))
    def inspect(path, cancel_event=None):
        if path.name == 'bad':
            raise ValueError('bad media')
        return MediaFile(path)
    monkeypatch.setattr(service, 'inspect', inspect)
    events = []
    results = InspectionBatch(service).run(tuple(map(Path, ['first', 'bad', 'last'])), threading.Event(), events.append)
    assert [result.status for result in results] == [Status.COMPLETED, Status.FAILED, Status.COMPLETED]
    assert [event.status for event in events] == [Status.RUNNING, Status.COMPLETED, Status.RUNNING, Status.FAILED,
                                                Status.RUNNING, Status.COMPLETED]
    assert 'bad media' in results[1].error
    assert len(caplog.records) == 1


def test_cancel_keeps_completed_results_and_does_not_launch_pending(monkeypatch):
    service = MediaService(Binaries(Path('ffmpeg'), Path('ffprobe'), 'test'))
    calls = []
    def inspect(path, cancel_event=None):
        calls.append(path.name)
        if path.name == 'second':
            cancel_event.set()
            raise OperationCancelled()
        return MediaFile(path)
    monkeypatch.setattr(service, 'inspect', inspect)
    results = InspectionBatch(service).run(tuple(map(Path, ['first', 'second', 'third'])), threading.Event(), lambda _: None)
    assert calls == ['first', 'second']
    assert [r.status for r in results] == [Status.COMPLETED, Status.CANCELLED, Status.CANCELLED]
    assert results[0].media is not None
    assert results[1].media is None and results[2].media is None


def test_pre_cancelled_probe_never_launches(monkeypatch):
    event = threading.Event()
    event.set()
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.probe_service.subprocess.Popen',
                        lambda *a, **kw: pytest.fail('Cancelled probe launched'))
    with pytest.raises(OperationCancelled):
        run_cancellable_probe(['unused'], event)


def test_cancel_reaps_real_child_and_drains_large_pipes(monkeypatch):
    original = subprocess.Popen
    started = threading.Event()
    cancel = threading.Event()
    processes, errors = [], []
    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        started.set()
        return process
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.probe_service.subprocess.Popen', launch)
    def run():
        try:
            run_cancellable_probe([sys.executable, '-c',
                                   "import sys,time; sys.stdout.write('x'*200000); sys.stderr.write('y'*200000); time.sleep(30)"], cancel)
        except Exception as error:  # noqa: BLE001 - record the background outcome
            errors.append(error)
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert started.wait(5)
        cancel.set()
        thread.join(5)
        assert not thread.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], OperationCancelled)
        assert processes[0].poll() is not None
        assert processes[0].stdout.closed and processes[0].stderr.closed
    finally:
        cancel.set()
        thread.join(5)


def test_timeout_reaps_real_child(monkeypatch):
    original = subprocess.Popen
    processes = []
    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.probe_service.subprocess.Popen', launch)
    with pytest.raises(subprocess.TimeoutExpired):
        run_cancellable_probe([sys.executable, '-c', 'import time; time.sleep(30)'], threading.Event(), timeout=.1)
    assert processes[0].poll() is not None


def test_cancellable_probe_returns_complete_stdout_and_failure_stderr():
    result = run_cancellable_probe([sys.executable, '-c',
                                   "import sys; print('x'*200000); print('diagnostic'+'y'*200000, file=sys.stderr); sys.exit(2)"], threading.Event())
    assert result.returncode == 2
    assert len(result.stdout.strip()) == 200000
    assert 'diagnostic' in result.stderr
