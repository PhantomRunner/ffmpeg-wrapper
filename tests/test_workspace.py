"""Workspace persistence and navigation without changing operation services."""
import pytest
from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QApplication

from media_wrapper.ui.main_window import MainWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_workspace_roundtrip_and_reset(app, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    settings = QSettings(str(tmp_path / 'layout.ini'), QSettings.Format.IniFormat)
    window = MainWindow(layout_settings=settings)
    window.show()
    app.processEvents()
    window.workspace.horizontal.setSizes([250, 500, 400])
    window.navigation.setCurrentRow(2)
    window.workspace.timelines.setCurrentIndex(1)
    sizes = window.workspace.horizontal.sizes()
    window.close()
    restored = MainWindow(layout_settings=settings)
    restored.show()
    app.processEvents()
    assert restored.navigation.currentRow() == 2
    assert restored.workspace.timelines.currentIndex() == 1
    assert restored.workspace.horizontal.sizes() == sizes
    restored.workspace.reset_layout()
    assert restored.workspace.timelines.currentIndex() == 0
    assert restored.workspace.horizontal.count() == 3
    assert restored.workspace.vertical.count() == 2
    for index in range(6):
        restored.navigation.setCurrentRow(index)
        assert restored.pages.currentIndex() == index
        assert restored.files_view.isVisible()
    restored.close()


def test_corrupt_layout_falls_back(app, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    settings = QSettings(str(tmp_path / 'layout.ini'), QSettings.Format.IniFormat)
    for key, value in {'version': '1', 'mode': 'broken', 'timeline': 99,
                       'horizontal': QByteArray(b'bad'), 'vertical': 'wrong type'}.items():
        settings.setValue('workspace/' + key, value)
    window = MainWindow(layout_settings=settings)
    window.show()
    app.processEvents()
    assert window.navigation.currentRow() == 0
    assert all(size > 0 for size in window.workspace.horizontal.sizes())
    window.close()
