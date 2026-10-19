from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QMessageBox

from media_wrapper.application.task_queue import TaskQueue
from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.ui.main_window import MainWindow


def test_clear_history_keeps_active_pending_files_and_binary_references(sample):
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    queue = TaskQueue()
    records = [queue.add(plan, binaries) for _ in range(5)]
    for record, status in zip(records, (TaskStatus.COMPLETED, TaskStatus.FAILED,
                                        TaskStatus.CANCELLED, TaskStatus.RUNNING, TaskStatus.PENDING), strict=True):
        record.status = status
    records[3].log = 'active diagnostics'
    queue.active = SimpleNamespace(record=records[3])
    queue.running = True
    plan.output.path.write_bytes(b'keep output')
    source = plan.media.path.read_bytes()
    assert queue.clear_history() == tuple(r.id for r in records[:3])
    assert queue.records == records[3:]
    assert set(queue._binaries) == {r.id for r in records[3:]}
    assert queue.running and queue.active.record is records[3]
    assert records[3].log == 'active diagnostics'
    assert plan.output.path.read_bytes() == b'keep output'
    assert plan.media.path.read_bytes() == source
    assert queue.clear_history() == ()
    # A terminal record still owned by an active task is protected until cleanup.
    records[3].status = TaskStatus.COMPLETED
    assert queue.finished_history_ids() == ()
    queue.active = None
    app.processEvents()


def test_confirmation_snapshot_cancel_and_empty_state(sample, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    queue = window.model.queue
    binaries, plan = sample
    assert not window.queue_view.clear_history.isEnabled()
    first = queue.add(plan, binaries)
    first.status = TaskStatus.FAILED
    second = queue.add(plan, binaries)
    window.render_queue()
    assert window.queue_view.clear_history.isEnabled()
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.StandardButton.No)
    window.clear_queue_history()
    assert len(queue.records) == 2

    def confirm(*args):
        assert '1 finished' in args[2]
        assert 'will not be deleted' in args[2]
        second.status = TaskStatus.COMPLETED
        return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QMessageBox, 'question', confirm)
    window.clear_queue_history()
    assert queue.records == [second]
    assert window.queue_view.history_summary.text() == '1 finished session entries'
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.StandardButton.Yes)
    window.clear_queue_history()
    assert not queue.records
    assert not window.queue_view.clear_history.isEnabled()
    assert not window.queue_view.details.toPlainText()
    window.clear_queue_history()
    window.close()
    app.processEvents()


def test_clearing_finished_entries_during_real_processing(sample):
    import time
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    queue = TaskQueue()
    old = queue.add(plan, binaries)
    old.status = TaskStatus.CANCELLED
    running = queue.add(plan, binaries)
    queue.start()
    assert queue.active is not None
    assert queue.clear_history() == (old.id,)
    assert queue.records == [running]
    deadline = time.monotonic() + 10
    while queue.running and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert not queue.running
    assert running.status == TaskStatus.COMPLETED, running.error
    assert running.result is not None and plan.output.path.exists()
