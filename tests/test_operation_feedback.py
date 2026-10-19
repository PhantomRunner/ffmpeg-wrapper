from PySide6.QtWidgets import QApplication

from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.ui.main_window import MainWindow


def test_notifications_deduplicate_preserve_errors_and_gate_output(sample, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    _, plan = sample
    failed = TaskRecord(plan, status=TaskStatus.FAILED, error='Choose a writable destination')
    completed = TaskRecord(plan, status=TaskStatus.COMPLETED)
    feedback = window.feedback
    feedback.observe([failed, completed])
    feedback.observe([failed, completed])
    assert len(feedback.notices) == 2
    assert 'Failed' in feedback.message.text()
    assert 'writable' in feedback.details.toPlainText()
    assert not feedback.open_button.isEnabled()
    feedback.acknowledge()
    assert 'awaiting verification' in feedback.message.text()
    # A completion with verified metadata is the only source of an open-output action.
    verified = TaskRecord(plan, status=TaskStatus.COMPLETED, result=plan.media)
    feedback.observe([verified])
    assert feedback.open_button.isEnabled()
    assert 'output verified' in feedback.message.text()
    assert str(plan.output.path) in feedback.message.text()
    feedback.queue_button.click()
    assert window.navigation.currentRow() == 4
    window.close()
    app.processEvents()
