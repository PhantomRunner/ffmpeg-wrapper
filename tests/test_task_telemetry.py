import time

import pytest
from PySide6.QtWidgets import QApplication

from media_wrapper.application.conversion_service import conversion_plan
from media_wrapper.application.operation_task import OperationTask
from media_wrapper.application.task_queue import TaskQueue
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskRecord, TaskStatus


def test_elapsed_uses_monotonic_clock_and_stops_at_terminal(sample, monkeypatch):
    clock = iter((10.0, 13.0, 20.0))
    monkeypatch.setattr('media_wrapper.domain.tasks.monotonic', lambda: next(clock))
    record = TaskRecord(sample[1])
    assert record.elapsed is None
    record.transition(TaskStatus.PREPARING)
    assert record.elapsed == 3
    record.transition(TaskStatus.FAILED)
    assert record.elapsed == 10
    assert record.created_at and record.started_at and record.finished_at


def test_batch_insertion_emits_once_and_fingerprint_blocks_changed_source(sample):
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    queue = TaskQueue()
    notices = []
    queue.changed.connect(lambda: notices.append(True))
    records = queue.add_many((plan, plan), binaries)
    assert len(notices) == 1 and len({r.id for r in records}) == 2
    record = TaskRecord(plan, source_fingerprint=(0, 0))
    task = OperationTask(record, binaries)
    with pytest.raises(ValueError, match='Source changed'):
        task._prepare()
    app.processEvents()


def test_two_pass_records_actual_commands_and_elapsed(video_sample, tmp_path):
    app = QApplication.instance() or QApplication([])
    binaries, base = video_sample
    request = ConversionRequest(tmp_path / 'budget.mp4', Container.MP4,
                                tuple((s.index, 'libx264' if s.kind == 'video' else 'aac') for s in base.media.streams),
                                mode='target', target_size_bytes=1048576, preset='ultrafast')
    queue = TaskQueue()
    record = queue.add(conversion_plan(base.media, request), binaries)
    queue.start()
    deadline = time.monotonic() + 20
    while queue.running and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert not queue.running and record.status == TaskStatus.COMPLETED, record.error
    assert record.pass_count == record.pass_index == len(record.commands) == 2
    assert record.elapsed >= 0 and record.source_fingerprint
    assert record.commands[0] != record.commands[1]
