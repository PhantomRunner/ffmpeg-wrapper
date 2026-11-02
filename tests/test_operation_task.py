import subprocess
import time

import pytest
from PySide6.QtWidgets import QApplication

from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_task import OperationTask
from media_wrapper.domain.operations import (
    OutputTarget,
    StreamSelection,
)
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.output_publication import publish_output


def wait(app, predicate):
    deadline = time.monotonic() + 10
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.001)
    assert predicate()



def test_verified_staged_remux(sample):
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    task = OperationTask(TaskRecord(plan), binaries)
    finished = []
    task.finished.connect(lambda *r: finished.append(r))
    task.start()
    wait(app, lambda: bool(finished))
    assert finished[0][0] and task.record.status == TaskStatus.COMPLETED
    assert task.record.result.path == plan.output.path
    assert task.record.result.streams[0].codec == 'pcm_s16le'
    assert not task.record.partial_path.exists()
    assert '-progress' in task.record.command
    loglevel = task.record.command.index('-loglevel')
    assert task.record.command[loglevel + 1] == 'error'
    assert task.thread is None


def test_process_failure_keeps_only_stderr_in_failure_detail(sample, monkeypatch):
    import sys

    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    task = OperationTask(TaskRecord(plan), binaries)
    message = 'Error opening encoder: Invalid argument'
    script = "import sys; print('frame=10\\nprogress=end'); print(sys.argv[1], file=sys.stderr); sys.exit(1)"
    monkeypatch.setattr(task, '_prepare', lambda: (plan, [sys.executable, '-c', script, message]))
    results = []
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.status == TaskStatus.FAILED
    assert task.record.failure_detail == message
    assert 'Arguments:' in task.record.log
    assert 'FFmpeg exit code: 1' in task.record.log
    assert 'selected FFmpeg/FFprobe process failed' in task.record.error


def test_preparation_failure_keeps_original_message(sample, monkeypatch):
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    task = OperationTask(TaskRecord(plan), binaries)
    message = 'Destination already exists'

    def fail():
        raise ValueError(message)

    monkeypatch.setattr(task, '_prepare', fail)
    results = []
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.failure_detail == message
    assert task.record.status == TaskStatus.FAILED


def test_publication_never_overwrites(tmp_path):
    temporary, destination = tmp_path/'partial', tmp_path/'final'
    temporary.write_bytes(b'new')
    destination.write_bytes(b'original')
    with pytest.raises(FileExistsError):
        publish_output(temporary, destination)
    assert temporary.read_bytes() == b'new'
    assert destination.read_bytes() == b'original'


def test_cancel_during_preparation_never_publishes(sample):
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    task = OperationTask(TaskRecord(plan), binaries)
    finished = []
    task.finished.connect(lambda *r: finished.append(r))
    task.start()
    task.cancel()
    wait(app, lambda: bool(finished))
    assert task.record.status == TaskStatus.CANCELLED
    assert not plan.output.path.exists()
    assert task.thread is None


def test_destination_appearing_at_publication_is_preserved(sample, monkeypatch):
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    def collide(temporary, destination):
        destination.write_bytes(b'other application')
        return publish_output(temporary, destination)
    monkeypatch.setattr('media_wrapper.application.operation_task.publish_output', collide)
    task = OperationTask(TaskRecord(plan), binaries)
    results = []
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.status == TaskStatus.FAILED
    assert task.record.partial_path.is_file()
    assert plan.output.path.read_bytes() == b'other application'
    assert task.record.result is None


@pytest.mark.parametrize('mode', ['crash', 'cancel', 'invalid_output'])
def test_failed_or_cancelled_output_is_never_published(sample, monkeypatch, mode):
    import sys
    from dataclasses import replace

    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    temporary = plan.output.path.with_name('failed.partial.mkv')
    prepared = replace(plan, output=replace(plan.output, temporary_path=temporary))
    task = OperationTask(TaskRecord(plan), binaries)
    script = "import pathlib,sys,time; pathlib.Path(sys.argv[1]).write_bytes(b'partial'); print('ready',flush=True); "
    script += {'crash': 'sys.exit(2)', 'cancel': 'time.sleep(60)', 'invalid_output': 'sys.exit(0)'}[mode]
    monkeypatch.setattr(task, '_prepare', lambda: (prepared, [sys.executable, '-u', '-c', script, str(temporary)]))
    results = []
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    if mode == 'cancel':
        wait(app, lambda: temporary.exists())
        task.cancel()
    wait(app, lambda: bool(results))
    assert task.record.status == (TaskStatus.CANCELLED if mode == 'cancel' else TaskStatus.FAILED)
    assert task.record.result is None and not plan.output.path.exists()
    assert temporary.read_bytes() == b'partial'


def test_selected_tracks_real_remux_and_rejected_incompatibility(sample, tmp_path):
    from dataclasses import replace

    app = QApplication.instance() or QApplication([])
    binaries, original = sample
    source = tmp_path/'two tracks.mkv'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-i', str(original.media.path),
                    '-map', '0:a', '-map', '0:a', '-c', 'copy', '-n', str(source)],
                   check=True, capture_output=True, timeout=15)
    media = MediaService(binaries).inspect(source)
    plan = replace(original, media=media, streams=(StreamSelection(1),))
    task = OperationTask(TaskRecord(plan), binaries)
    results = []
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.status == TaskStatus.COMPLETED
    assert len(task.record.result.streams) == 1
    assert '0:1' in task.record.command and '0:0' not in task.record.command
    invalid = replace(plan, output=OutputTarget(tmp_path/'unsupported.mp4', Container.MP4))
    task = OperationTask(TaskRecord(invalid), binaries)
    results.clear()
    task.finished.connect(lambda *r: results.append(r))
    task.start()
    wait(app, lambda: bool(results))
    assert task.record.status == TaskStatus.FAILED
    assert not invalid.output.path.exists()
