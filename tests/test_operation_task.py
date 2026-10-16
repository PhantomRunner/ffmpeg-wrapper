import subprocess
import time

import pytest
from PySide6.QtWidgets import QApplication

from media_wrapper.application.media_service import MediaService
from media_wrapper.application.operation_task import OperationTask
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    StreamSelection,
)
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.ffmpeg.binary_resolver import resolve
from media_wrapper.infrastructure.ffmpeg.output_publication import publish_output


def wait(app, predicate):
    deadline = time.monotonic() + 10
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.001)
    assert predicate()


@pytest.fixture
def sample(tmp_path):
    try:
        binaries = resolve()
    except (FileNotFoundError, RuntimeError) as error:
        pytest.skip(str(error))
    source = tmp_path/'source ü.wav'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=0.1',
                    '-n', str(source)], check=True, capture_output=True, timeout=15)
    media = MediaService(binaries).inspect(source)
    plan = OperationPlan(MediaOperation.REMUX, media, (StreamSelection(0),),
                         OutputTarget(tmp_path/'result.mkv', Container.MATROSKA))
    return binaries, plan


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
    assert task.thread is None


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
