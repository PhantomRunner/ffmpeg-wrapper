"""Queue result indicators open only the error belonging to the selected task."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    StreamSelection,
)
from media_wrapper.domain.progress import Progress
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.ui.main_window import MainWindow
from media_wrapper.ui.models.tasks import TaskStatusDelegate
from media_wrapper.ui.theme.tokens import COLORS


@pytest.fixture
def queue_window(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    records = []
    for status in TaskStatus:
        media = MediaFile(tmp_path / f'{status.value}.mkv', streams=(MediaStream(0, 'video', 'h264'),))
        plan = OperationPlan(MediaOperation.CONVERT, media, (StreamSelection(0),),
                             OutputTarget(tmp_path / f'{status.value}-output.mkv', Container.MATROSKA))
        records.append(TaskRecord(plan, status=status, progress=Progress(percent=42, speed=1.5, eta=12),
                                  error='Wrapped application error. Check the diagnostic log.',
                                  failure_detail=f'Error opening output file <{status.value}>: Permission denied',
                                  command=('ffmpeg', '-i', str(media.path)),
                                  log='Arguments: [ffmpeg]\nframe=10\nFFmpeg exit code: 1'))
    window.model.queue.records.extend(records)
    window.navigation.setCurrentRow(4)
    window.render_queue()
    window.resize(1280, 720)
    window.show()
    for _ in range(3):
        app.processEvents()
    yield app, window, records
    if window.queue_view.error_dialog is not None:
        window.queue_view.error_dialog.close()
    window.close()
    app.processEvents()


def test_only_failed_indicator_opens_error_dialog(queue_window):
    app, window, records = queue_window
    view = window.queue_view
    assert not hasattr(view, 'details')
    assert not hasattr(view, 'details_toggle')
    for row, record in enumerate(records):
        index = view.task_model.index(row, 2)
        view.table.scrollTo(index)
        app.processEvents()
        point = TaskStatusDelegate.indicator_rect(view.table.visualRect(index)).center()
        assert view.table.viewport().rect().contains(point)
        QTest.mouseMove(view.table.viewport(), point)
        app.processEvents()
        clickable = record.status == TaskStatus.FAILED
        assert view.table.viewport().cursor().shape() == (
            Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)
        QTest.mouseClick(view.table.viewport(), Qt.MouseButton.LeftButton, pos=point)
        app.processEvents()
        if clickable:
            assert view.error_dialog.isVisible() and view.error_dialog.isModal()
            assert view.error_message.toPlainText() == record.failure_detail
            QTest.keyClick(view.error_dialog, Qt.Key.Key_Escape)
            assert not view.error_dialog.isVisible()
        else:
            assert view.error_dialog is None or not view.error_dialog.isVisible()
        if record.status == TaskStatus.COMPLETED:
            pixel = view.table.viewport().grab().toImage().pixelColor(point)
            assert pixel.name().upper() == COLORS['success']


def test_error_indicator_supports_keyboard_and_live_state_updates(queue_window):
    app, window, records = queue_window
    view = window.queue_view
    record = records[0]
    index = view.task_model.index(0, 2)
    view.table.setCurrentIndex(index)
    view.table.setFocus()
    QTest.keyClick(view.table, Qt.Key.Key_Return)
    assert view.error_dialog is None
    record.status = TaskStatus.RUNNING
    window.render_queue()
    assert '42.0%' in window.output.toPlainText()
    record.status = TaskStatus.FAILED
    record.failure_detail = 'Unknown encoder: unavailable_encoder'
    window.render_queue()
    QTest.keyClick(view.table, Qt.Key.Key_Return)
    app.processEvents()
    assert view.error_dialog.isVisible()
    assert view.error_message.toPlainText() == record.failure_detail
    view.error_dialog.accept()
    window.navigation.setCurrentRow(2)
    window.navigation.setCurrentRow(4)
    assert window.output.toPlainText().endswith('Failed')
