from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit
from test_flat_workbench import flat_window, wait  # noqa: F401 - shared pytest fixture

from media_wrapper.domain.operations import MediaOperation


def test_native_window_output_is_pinned_and_delete_is_scoped(flat_window, sample):  # noqa: F811
    app, window = flat_window
    window.controller.import_sources((sample[1].media.path,))
    wait(app, lambda: not window.controller.busy)
    window.render()
    assert not window.windowFlags() & Qt.WindowType.FramelessWindowHint
    window.shell.set_page('workspace')
    window.sources.table.selectRow(0)
    template = window.inspector.fields['template'].control
    assert isinstance(template, QLineEdit)
    window.activateWindow()
    template.setFocus()
    QTest.keyClick(template, Qt.Key.Key_Delete)
    assert len(window.draft.items) == 1
    window.inspector.scroll.verticalScrollBar().setValue(window.inspector.scroll.verticalScrollBar().maximum())
    output = window.inspector.groups['output'][0]
    assert output.isVisible()
    assert window.rect().contains(output.mapTo(window, output.rect().bottomRight()))
    window.sources.table.setFocus()
    QTest.keyClick(window.sources.table, Qt.Key.Key_Delete)
    app.processEvents()
    assert not window.draft.items and sample[1].media.path.exists()


def test_supported_window_widths_and_keyboard_navigation(flat_window):  # noqa: F811
    app, window = flat_window
    for width in (900, 1024, 1280, 1600):
        window.resize(width, 760)
        for route in ('workspace', 'queue', 'settings'):
            window.shell.set_page(route)
            app.processEvents()
            assert window.width() == width
            if route == 'workspace':
                assert window.start.isVisible()
                assert window.rect().contains(window.start.mapTo(window, window.start.rect().bottomRight()))
            else:
                assert not window.toolbar.add_files.isVisible() and not window.start.isVisible()
    window.activateWindow()
    QTest.keyClick(window, Qt.Key.Key_1, Qt.KeyboardModifier.AltModifier)
    assert window.shell.page == 'workspace'
    QTest.keyClick(window, Qt.Key.Key_2, Qt.KeyboardModifier.AltModifier)
    assert window.shell.page == 'queue'


def test_omitted_video_does_not_show_irrelevant_video_controls(flat_window, video_sample):  # noqa: F811
    app, window = flat_window
    window.controller.import_sources((video_sample[1].media.path,))
    wait(app, lambda: not window.controller.busy)
    window.set_operation(MediaOperation.COMPRESS)
    item = next(iter(window.draft.items.values()))
    tracks = tuple((s.index, 'omit' if s.kind == 'video' else 'aac') for s in item.media.streams)
    window.controller.patch('tracks', tracks)
    window.render()
    assert window.inspector.fields['video_encoder'].isHidden()
    assert window.inspector.fields['crf'].isHidden()
    assert not window.inspector.groups['audio'][0].isHidden()
    assert QApplication.instance() is app
