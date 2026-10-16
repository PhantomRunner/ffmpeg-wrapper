from dataclasses import replace

from PySide6.QtWidgets import QApplication
from test_operation_task import wait

from media_wrapper.application.task_queue import TaskQueue
from media_wrapper.domain.tasks import TaskStatus


def test_queue_failure_isolation_and_retry(sample):
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    queue = TaskQueue()
    plan.output.path.write_bytes(b'existing')
    failed = queue.add(plan, binaries)
    next_plan = replace(plan, output=replace(plan.output, path=plan.output.path.with_name('second.mkv')))
    completed = queue.add(next_plan, binaries)
    seen = []
    queue.changed.connect(lambda: seen.append(tuple(r.status for r in queue.records)))
    queue.start()
    wait(app, lambda: not queue.running)
    assert failed.status == TaskStatus.FAILED and completed.status == TaskStatus.COMPLETED
    assert all(sum(s in (TaskStatus.RUNNING, TaskStatus.PREPARING) for s in states) <= 1 for states in seen)
    assert failed.error and completed.log
    plan.output.path.unlink()  # User resolves collision before retry.
    retried = queue.retry(failed.id)
    queue.start()
    wait(app, lambda: not queue.running)
    assert retried.status == TaskStatus.COMPLETED and retried.id != failed.id
    assert failed.status == TaskStatus.FAILED and failed.error


def test_cancel_pending_and_active_then_continue(sample):
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    queue = TaskQueue()
    first = queue.add(plan, binaries)
    pending = queue.add(plan, binaries)
    third = queue.add(replace(plan, output=replace(plan.output, path=plan.output.path.with_name('third.mkv'))), binaries)
    queue.cancel(pending.id)
    queue.start()
    queue.cancel(first.id)
    wait(app, lambda: not queue.running)
    assert [r.status for r in queue.records] == [TaskStatus.CANCELLED, TaskStatus.CANCELLED, TaskStatus.COMPLETED]
    assert third.result is not None and not plan.output.path.exists()
