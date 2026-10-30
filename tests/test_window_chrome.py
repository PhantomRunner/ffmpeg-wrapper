"""Custom chrome keeps window actions, resizing and modal choices functional."""
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QLabel, QMessageBox

from media_wrapper.ui.main_window import MainWindow
from media_wrapper.ui.theme.tokens import COLORS


@pytest.fixture
def window(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    shell = MainWindow()
    shell.show()
    app.processEvents()
    yield shell
    shell.close()
    app.processEvents()


def test_custom_chrome_maximizes_restores_and_closes(window):
    header = window.workspace.title_bar
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    QTest.mouseClick(header.maximize_button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert window.isMaximized()
    assert header.maximize_button.accessibleName() == 'Restore window'
    QTest.mouseClick(header.maximize_button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert not window.isMaximized()
    assert header.maximize_button.accessibleName() == 'Maximize window'
    QTest.mouseClick(header.close_button, Qt.MouseButton.LeftButton)
    assert not window.isVisible()


def test_resize_fallback_preserves_minimum_size(window, monkeypatch):
    handle = window.windowHandle()
    monkeypatch.setattr(handle, 'startSystemResize', lambda edges: False)
    initial = window.size()
    origin = QPoint(window.width() - 2, window.height() - 2)
    global_origin = window.mapToGlobal(origin)
    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(origin), QPointF(global_origin),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, press)
    target = global_origin + QPoint(80, 60)
    move = QMouseEvent(QEvent.Type.MouseMove, QPointF(origin + QPoint(80, 60)), QPointF(target),
                       Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, move)
    assert window.width() == initial.width() + 80
    assert window.height() == initial.height() + 60
    far = global_origin - QPoint(5000, 5000)
    shrink = QMouseEvent(QEvent.Type.MouseMove, QPointF(-5000, -5000), QPointF(far),
                         Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, shrink)
    assert window.size() == window.minimumSize()
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton)


def test_file_picker_is_themed_and_keeps_keyboard_cancel(window, tmp_path):
    dialog = QFileDialog(window, 'Import media', str(tmp_path))
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
    dialog.show()
    QApplication.processEvents()
    assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert dialog.palette().color(QPalette.ColorRole.Window).name().upper() == COLORS['panel']
    title = dialog.findChild(QLabel, 'studioDialogTitle')
    assert title.text() == 'Import media'
    dialog.setWindowTitle('Choose output')
    assert title.text() == 'Choose output'
    dialog.resize(760, 520)
    QApplication.processEvents()
    header = dialog.findChild(QFrame, 'dialogHeader')
    assert header.geometry().right() == dialog.width() - 11
    assert header.geometry().bottom() < dialog.findChild(QLabel, 'fileNameLabel').geometry().top()
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert dialog.result() == QFileDialog.DialogCode.Rejected
    assert not dialog.isVisible()


@pytest.mark.parametrize('choice', [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No])
def test_themed_confirmation_preserves_modal_result(window, choice):
    observed = {}

    def choose():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            try:
                observed['themed'] = dialog.property('studioDialog')
                header = dialog.findChild(QFrame, 'dialogHeader')
                label = dialog.findChild(QLabel, 'qt_msgbox_label')
                observed['text'] = label.text()
                observed['body_visible'] = label.isVisible()
                observed['body_below_header'] = label.geometry().top() > header.geometry().bottom()
            finally:
                dialog.button(choice).click()

    QTimer.singleShot(0, choose)
    answer = QMessageBox.question(window, 'Clear history', 'Remove finished entries?',
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
    assert answer == choice
    assert observed == {'themed': True, 'text': 'Remove finished entries?',
                        'body_visible': True, 'body_below_header': True}
