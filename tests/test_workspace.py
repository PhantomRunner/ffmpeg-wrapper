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
        assert restored.workspace.preview.isVisible() == (index == 0)
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


@pytest.mark.parametrize('width,height,show_method', [
    (960, 640, 'show'),
    (1920, 1080, 'show'),
    (2560, 1440, 'show'),
    (1280, 720, 'showMaximized'),
    (1280, 720, 'showFullScreen'),
])
def test_navigation_keeps_compact_height_across_tabs(app, monkeypatch, width, height, show_method):
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    window.resize(width, height)
    getattr(window, show_method)()
    navigation_bar = window.navigation.parentWidget()
    try:
        for mode in (0, 1, 4, 5, 2, 3, 1, 0):
            window.navigation.setCurrentRow(mode)
            for _ in range(3):
                app.processEvents()
            assert navigation_bar.height() == navigation_bar.sizeHint().height()
            assert window.workspace.title_bar.height() == window.workspace.title_bar.sizeHint().height()
            footer = window.workspace.operation_footer
            assert footer.isVisible() == (mode < 5)
            if footer.isVisible():
                assert window.workspace.vertical.geometry().bottom() < footer.y()
                assert footer.geometry().bottom() == window.workspace.height() - 1
            else:
                assert window.workspace.vertical.geometry().bottom() == window.workspace.height() - 1
    finally:
        window.close()


@pytest.mark.parametrize('width,height', [(960, 640), (1920, 1080)])
def test_operation_footer_is_shared_by_encoding_and_queue(app, monkeypatch, width, height):
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    window.resize(width, height)
    window.show()
    footer = window.workspace.operation_footer
    footer.toggle.setChecked(True)
    try:
        for mode in (2, 3, 4, 2):
            window.navigation.setCurrentRow(mode)
            for _ in range(3):
                app.processEvents()
            assert footer.isVisible() and window.output.isVisible()
            assert footer.isAncestorOf(window.output)
            assert not window.workspace.preview.isVisible()
            assert not window.workspace.preview_toggle.isVisible()
            assert window.workspace.vertical.geometry().bottom() < footer.y()
            assert window.rect().contains(window.output.mapTo(window, window.output.rect().bottomRight()))
        footer.toggle.click()
        assert not window.output.isVisible()
    finally:
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


@pytest.mark.parametrize('operation_name', ['convert', 'compress'])
@pytest.mark.parametrize('width', [280, 320, 420])
def test_progressive_inspector_fits_narrow_panel(app, tmp_path, operation_name, width):
    from media_wrapper.domain.draft import DraftState
    from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
    from media_wrapper.domain.media import MediaFile, MediaStream
    from media_wrapper.domain.operations import MediaOperation
    from media_wrapper.ui.settings_inspector import SettingsInspector
    from media_wrapper.ui.theme import apply_theme

    draft = DraftState(multiple_outputs=True)
    source_path = tmp_path / ('Long-recording-name-' * 9 + '.mkv')
    draft.add((source_path,))
    media = MediaFile(source_path, streams=(MediaStream(0, 'video', 'h264'), MediaStream(1, 'audio', 'aac')))
    draft.inspected(InspectionRecord(source_path, InspectionStatus.COMPLETED, media))
    draft.operation = MediaOperation(operation_name)
    view = SettingsInspector(progressive=True)
    apply_theme(view)
    view.resize(width, 500)
    view.show()

    try:
        for tab, page in enumerate(('Quick', 'Custom', 'Advanced')):
            view.tabs.setCurrentIndex(tab)
            for mode in ('quality', 'bitrate', 'target'):
                draft.patch('mode', mode)
                view.render(draft, named_presets={})
                view.output_preview.set_content(str(source_path.with_suffix('.mp4')), single_line=True)
                for _ in range(3):
                    app.processEvents()
                assert view.tabs.tabText(tab) == page
                assert view.width() == width
                body, viewport = view.scroll.widget(), view.scroll.viewport()
                context = f'{page}, {mode}: body {body.width()} px, viewport {viewport.width()} px'
                if view.scroll.horizontalScrollBar().maximum():
                    sections = {name: box.minimumSizeHint().width() for name, (box, _) in view.groups.items()
                                if box.isVisible()}
                    pytest.fail(f'{context}; visible section minimum widths {sections}')
                assert body.width() <= viewport.width(), context
                assert view.output_preview.isVisible()
                assert view.output_preview.toolTip() == str(source_path.with_suffix('.mp4'))
                fields = [view.intent_field, view.preset_field, *view.fields.values(), view.size_limit]
                for field in (field for field in fields if field.isVisible()):
                    assert field.geometry().right() < field.parentWidget().width()
                    assert field.control.geometry().right() < field.control.parentWidget().width()
    finally:
        view.close()
