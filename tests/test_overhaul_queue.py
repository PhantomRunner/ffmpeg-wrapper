"""Durable-state acceptance independently of shell route and native package build."""
import json
import os
import select
import signal
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from media_wrapper.application.task_queue import TaskQueue
from media_wrapper.domain.history_document import parse_record, record_payload
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.queue_store import QueueStore


def local_queue(tmp_path):
    queue = TaskQueue()
    queue.enable_persistence(tmp_path / 'queue.sqlite3', tmp_path / 'attempt-logs')
    return queue


def test_pending_order_policy_and_full_logs_survive_restart(sample, tmp_path):
    binaries, plan = sample
    queue = local_queue(tmp_path)
    another = local_queue(tmp_path)
    assert another.persistence_error
    assert another.add_many((plan,), binaries) == ()
    assert not another.running
    first = queue.add(plan, binaries)
    second = queue.add(replace(plan, output=replace(plan.output, path=tmp_path / 'another.mkv')), binaries)
    assert queue.move_pending(second.id, -1)
    queue.set_stop_on_error(True)
    first.append_log('first line\n' + 'x' * 40000)
    assert len(first.log) == 16000
    queue.close_store()

    queue = local_queue(tmp_path)
    try:
        assert not queue.running
        assert [job.id for job in queue.records] == [second.id, first.id]
        assert queue.records[1].log_path.read_text().startswith('first line\n')
        assert queue.stop_on_error
        assert queue.remove_pending((second.id,)) == (second.id,)
    finally:
        queue.close_store()

    queue = local_queue(tmp_path)
    try:
        assert [job.id for job in queue.records] == [first.id]
    finally:
        queue.close_store()


@pytest.mark.parametrize('publish', [True, False])
def test_reconciliation_only_completes_the_verified_file(sample, tmp_path, publish):
    _, plan = sample
    staged = tmp_path / '.staged.mkv'
    staged.write_bytes(b'verified snapshot')
    partial = TaskRecord(plan, partial_path=staged)
    partial.transition(TaskStatus.PREPARING)
    partial.transition(TaskStatus.RUNNING)
    store = QueueStore(tmp_path / 'queue.sqlite3', tmp_path / 'attempt-logs')
    try:
        store.add((partial,))
        result = replace(plan.media, path=staged, size_bytes=staged.stat().st_size)
        store.before_publish(partial, staged, plan.output.path, result)
        if publish:
            staged.rename(plan.output.path)
        else:
            plan.output.path.write_bytes(staged.read_bytes())
    finally:
        store.close()

    queue = local_queue(tmp_path)
    try:
        restored, = queue.records
        assert restored.status == (TaskStatus.COMPLETED if publish else TaskStatus.INTERRUPTED)
        assert bool(restored.result) is publish
        assert plan.output.path.read_bytes() == b'verified snapshot'
        assert staged.exists() is not publish
        assert not queue.running
    finally:
        queue.close_store()


def test_old_history_snapshot_read_and_migrated_once(sample, tmp_path):
    _, plan = sample
    record = TaskRecord(plan, status=TaskStatus.FAILED)
    old = json.loads(json.dumps(record_payload(record)))
    for field in ('profile', 'pixel_format', 'bit_depth', 'sample_aspect_ratio', 'display_aspect_ratio', 'color_space',
                  'color_transfer', 'color_primaries', 'color_range', 'dispositions', 'tags', 'side_data', 'duration'):
        old['media']['streams'][0].pop(field)
    for field in ('sample_rate', 'channels', 'channel_layout', 'codec_profile', 'level', 'pixel_format',
                  'color_space', 'color_transfer', 'color_primaries', 'color_range'):
        old['intent']['streams'][0]['profile'].pop(field)
    restored = parse_record(old)

    queue = local_queue(tmp_path)
    try:
        queue.import_legacy_history((restored,))
        assert [attempt.id for attempt in queue.records] == [restored.id]
        queue.clear_history((restored.id,))
    finally:
        queue.close_store()
    queue = local_queue(tmp_path)
    try:
        queue.import_legacy_history((restored,))
        assert not queue.records
    finally:
        queue.close_store()


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux parent-death smoke test')
def test_killing_parent_ends_its_owned_child():
    # The inherited output pipe closes when both processes have exited.
    helper = Path(__file__).parents[1] / 'src' / 'media_wrapper' / 'infrastructure' / 'process_lifetime.py'
    script = '''
import os, subprocess, sys, time
command = [sys.executable, '-I', '-S', sys.argv[1], '--media-wrapper-owned-child',
           str(os.getpid()), sys.executable, '-u', '-c',
           'import os, time; print(os.getpid(), flush=True); time.sleep(30)']
subprocess.Popen(command)
time.sleep(30)
'''
    process = subprocess.Popen([sys.executable, '-c', script, str(helper)], stdout=subprocess.PIPE)
    child_pid = None
    child_ended = False
    try:
        assert select.select([process.stdout], [], [], 5)[0]
        child_pid = int(process.stdout.readline())
        process.kill()
        process.wait(timeout=5)
        assert select.select([process.stdout], [], [], 5)[0], f'Child {child_pid} retained the pipe after parent death'
        child_ended = not process.stdout.read(1)
        assert child_ended
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if child_pid is not None and not child_ended:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.stdout.close()


def test_recovered_queue_honors_failure_policy_and_resume_is_explicit(sample, tmp_path):
    from PySide6.QtWidgets import QApplication
    from test_operation_task import wait

    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    queue = local_queue(tmp_path)
    failed_path = tmp_path / 'missing.wav'
    try:
        bad = queue.add(replace(plan, media=replace(plan.media, path=failed_path),
                                output=replace(plan.output, path=tmp_path / 'failed.mkv')), binaries)
        good = queue.add(plan, binaries)
        queue.set_stop_on_error(True)
    finally:
        queue.close_store()

    queue = local_queue(tmp_path)
    try:
        assert all(record.status == TaskStatus.PENDING for record in queue.records)
        queue.bind_recovered_binaries(binaries)
        queue.start()
        wait(app, lambda: not queue.running)
        assert [record.status for record in queue.records] == [TaskStatus.FAILED, TaskStatus.PENDING]
        assert not plan.output.path.exists()
        queue.start()
        wait(app, lambda: not queue.running)
        assert queue.records[1].status == TaskStatus.COMPLETED
        assert queue.records[1].log_path.is_file()
    finally:
        queue.close_store()

    queue = local_queue(tmp_path)
    try:
        assert [record.id for record in queue.records] == [bad.id, good.id]
        assert [record.status for record in queue.records] == [TaskStatus.FAILED, TaskStatus.COMPLETED]
        assert queue.records[1].result.path == plan.output.path
        assert plan.media.path.is_file()
    finally:
        queue.close_store()


def test_stop_after_current_keeps_pending_snapshots(sample, tmp_path):
    from PySide6.QtWidgets import QApplication
    from test_operation_task import wait

    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    queue = local_queue(tmp_path)
    try:
        first = queue.add(plan, binaries)
        second = queue.add(replace(plan, output=replace(plan.output, path=tmp_path / 'after-stop.mkv')), binaries)
        queue.start()
        queue.stop_after_current()
        assert queue.running and queue.stop_requested
        wait(app, lambda: not queue.running)
        assert first.status == TaskStatus.COMPLETED
        assert second.status == TaskStatus.PENDING
        assert not second.plan.output.path.exists()
    finally:
        queue.close_store()


def test_results_filter_retains_comparable_terminal_outputs(sample, tmp_path):
    from PySide6.QtCore import QItemSelectionModel
    from PySide6.QtWidgets import QApplication

    from media_wrapper.ui.queue_page import QueuePage

    app = QApplication.instance() or QApplication([])
    _, plan = sample
    queue = TaskQueue()
    first = TaskRecord(plan, status=TaskStatus.COMPLETED, result=replace(plan.media, size_bytes=1200))
    other_path = tmp_path / 'second.mkv'
    other_plan = replace(plan, output=replace(plan.output, path=other_path))
    second = TaskRecord(other_plan, status=TaskStatus.INTERRUPTED)
    pending = TaskRecord(replace(other_plan, output=replace(plan.output, path=tmp_path / 'pending.mkv')))
    queue.records.extend((first, second, pending))

    page = QueuePage()
    page.set_results_mode(True)
    page.render(queue)
    assert page.proxy.rowCount() == 2
    page.table.selectionModel().select(page.proxy.index(1, 0),
                                       QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    app.processEvents()
    assert page.results.rowCount() == 2
    assert page.results.item(0, 9).text() == 'Verified'
    assert page.results.item(1, 2).text() == 'Interrupted'
    assert page.results.item(1, 9).text() == '—'
    assert '1.2 KiB verified output' in page.summary.text()
