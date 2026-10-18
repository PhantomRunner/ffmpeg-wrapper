"""Final workspace accessibility, critical action visibility and fallback checks."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from media_wrapper.ui.main_window import MainWindow


@pytest.mark.parametrize('width,height', [(960, 640), (1280, 720), (1920, 1080)])
def test_operation_actions_remain_visible_and_shortcuts_work(monkeypatch, width, height):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    window.resize(width, height)
    window.show()
    window.activateWindow()
    app.processEvents()
    for mode, view in ((1, window.remux_view), (2, window.convert_view), (3, window.compress_view)):
        window.navigation.setCurrentRow(mode)
        app.processEvents()
        assert window.size().width() == width
        for button in (view.enqueue_button, view.run_button, view.preview_button):
            assert button.isVisible()
            assert window.rect().contains(button.mapTo(window, button.rect().bottomRight()))
        view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
        assert view.enqueue_button.isVisible()
    shortcuts = {shortcut.key().toString() for shortcut in window.findChildren(QShortcut)}
    assert {'Ctrl+O', 'Ctrl+Return', 'Alt+1', 'Alt+6'} <= shortcuts
    QTest.keyClick(window, Qt.Key.Key_1, Qt.KeyboardModifier.AltModifier)
    app.processEvents()
    assert window.navigation.currentRow() == 0
    assert 'unavailable' in window.binary_summary.text()
    assert window.workspace.fallback.accessibleName() == 'Playback unavailable'
    assert not window.workspace.import_button.isEnabled()
    window.close()


def test_layout_version_fallback_and_saved_dimensions(monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings

    from media_wrapper.application.settings_service import SettingsService
    from media_wrapper.domain.preferences import Preferences
    from media_wrapper.infrastructure.settings_repository import SettingsRepository
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    service = SettingsService(SettingsRepository(tmp_path / 'preferences.json'))
    service.load()
    service.save(Preferences(width=1100, height=700))
    layout = QSettings(str(tmp_path / 'layout.ini'), QSettings.Format.IniFormat)
    layout.setValue('workspace/version', 'unknown')
    layout.setValue('workspace/mode', 999)
    window = MainWindow(settings_service=service, layout_settings=layout)
    window.show()
    app.processEvents()
    assert window.width() == 1100 and window.height() == 700
    assert window.navigation.currentRow() == 0
    window.close()
