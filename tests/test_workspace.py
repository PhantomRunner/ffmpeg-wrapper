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
    window.workspace.horizontal.setSizes([250, 700])
    window.navigation.setCurrentRow(2)
    window.workspace.vertical.setSizes([210, 480])
    app.processEvents()
    sizes = window.workspace.horizontal.sizes()
    heights = window.workspace.vertical.sizes()
    window.close()
    restored = MainWindow(layout_settings=settings)
    restored.show()
    app.processEvents()
    assert restored.navigation.currentRow() == 2
    assert restored.workspace.horizontal.sizes() == sizes
    assert restored.workspace.vertical.sizes() == heights
    assert restored.workspace.vertical.widget(0) is restored.workspace.preview
    assert restored.workspace.vertical.widget(1) is restored.workspace.horizontal
    restored.workspace.reset_layout()
    assert restored.workspace.horizontal.count() == 2
    assert not hasattr(restored.workspace, 'timelines')
    assert not hasattr(restored.workspace, 'media_timeline')
    for index in range(6):
        restored.navigation.setCurrentRow(index)
        assert restored.pages.currentIndex() == index
        assert restored.files_view.isVisible() == (index < 4)
        assert restored.workspace.preview.isVisible() == (index in (0, 2, 3))
        assert restored.queue_view.isVisible() == (index == 4)
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
    window.workspace.horizontal.setSizes([250, 700])
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


@pytest.mark.parametrize('title', ['Convert', 'Compress'])
@pytest.mark.parametrize('width', [280, 320, 420])
def test_encoding_form_fits_narrow_panel(app, title, width):
    from pathlib import Path

    from media_wrapper.domain.media import MediaFile
    from media_wrapper.ui.encoding_view import EncodingView

    view = EncodingView(title)
    view.resize(width, 500)
    view.set_media(MediaFile(Path('/tmp/' + 'long-source-name-' * 15 + '.mkv')), False)
    view.show()
    for expanded in (False, True):
        view.advanced_toggle.setChecked(expanded)
        for mode in ('quality', 'bitrate', 'target'):
            view.mode.setCurrentText(mode)
            for _ in range(3):
                app.processEvents()
            assert view.width() == width
            assert view.horizontalScrollBar().maximum() == 0
            assert view.widget().width() <= view.viewport().width()
            for field in (view.container, view.destination, view.advanced_toggle):
                assert field.geometry().right() < field.parentWidget().width()
    view.close()
