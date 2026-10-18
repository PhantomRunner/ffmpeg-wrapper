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
        assert restored.files_view.isVisible() == (index < 4)
        assert restored.workspace.preview.isVisible() == (index in (0, 2, 3))
        assert restored.workspace.timelines.isVisible() == (index != 5)
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


def test_navigation_preserves_edits_selection_and_per_mode_geometry(app, monkeypatch, tmp_path):
    from media_wrapper.domain.media import MediaFile, MediaStream
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    window.show()
    source = tmp_path / 'source.mkv'
    source.touch()
    window.model.add_files([source])
    window.model._inspected(MediaFile(source, streams=(MediaStream(0, 'video', 'h264'),)))
    window.navigation.setCurrentRow(2)
    window.convert_view.destination.setText(str(tmp_path / 'custom.mkv'))
    window.convert_view.video_width.setValue(640)
    window.workspace.horizontal.setSizes([250, 350, 450])
    app.processEvents()
    sizes = window.workspace.horizontal.sizes()
    selected = window.model.state.selected_streams
    for index in [3, 4, 5, 1, 0, 2]:
        window.navigation.setCurrentRow(index)
        app.processEvents()
    assert window.workspace.horizontal.sizes() == sizes
    assert window.convert_view.destination.text() == str(tmp_path / 'custom.mkv')
    assert window.convert_view.video_width.value() == 640
    assert window.model.state.selected_streams == selected
    window.close()
