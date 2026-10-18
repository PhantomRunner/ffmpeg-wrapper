"""UX regressions exercise real widgets and retain application safety checks."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.remux import Container
from media_wrapper.ui.main_window import MainWindow
from media_wrapper.ui.output_paths import suggest_output_path
from media_wrapper.ui.theme import apply_theme
from media_wrapper.ui.widgets.combo_box import ReadableComboBox


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('value,expected', [
    ('', ''), ('   ', '   '), ('/', '/'),
    ('/tmp/clip', '/tmp/clip.mp4'),
    ('/tmp/a.b/clip ü.final.mkv', '/tmp/a.b/clip ü.final.mp4'),
    ('/tmp/clip.MP4', '/tmp/clip.MP4'),
])
def test_output_suggestion(value, expected):
    assert suggest_output_path(value, Container.MP4) == expected


@pytest.mark.parametrize('mode', ['remux', 'convert', 'compress'])
def test_container_change_updates_path_and_invalidates_preview(app, monkeypatch, tmp_path, mode):
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    source = tmp_path / 'source.mkv'
    source.touch()
    window.model.add_files([source])
    window.model._inspected(MediaFile(source, streams=(MediaStream(0, 'video', 'h264'),)))
    view = getattr(window, mode + '_view')
    custom = tmp_path / 'custom ü.final.mkv'
    view.destination.setText(str(custom))
    view.preview.setPlainText('stale command')
    view.container.setCurrentIndex(1)
    assert view.destination.text() == str(custom.with_suffix('.mp4'))
    assert view.preview.toPlainText() == ''
    if mode == 'remux':
        assert window.model.state.destination == view.destination.text()
        assert window.model.state.container == Container.MP4
        assert not window.model.state.form_error
    else:
        assert view.request().destination == custom.with_suffix('.mp4')
    view.container.setCurrentIndex(0)
    assert view.destination.text() == str(custom)
    view.destination.clear()
    view.container.setCurrentIndex(1)
    assert view.destination.text() == ''
    assert not custom.exists()
    window.close()


def test_remux_manual_mismatch_and_suggested_collisions_remain_rejected(app, monkeypatch, tmp_path):
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'source')
    window.model.add_files([source])
    window.model._inspected(MediaFile(source, streams=(MediaStream(0, 'video', 'h264'),)))
    view = window.remux_view
    view.destination.setText(str(tmp_path / 'wrong.mp4'))
    assert 'must use .mkv' in window.model.state.form_error
    assert view.destination.text().endswith('wrong.mp4')
    view.destination.setText(str(source.with_suffix('.mkv')))
    view.container.setCurrentIndex(1)
    assert 'must differ' in window.model.state.form_error
    existing = tmp_path / 'existing.mkv'
    existing.write_bytes(b'keep')
    view.destination.setText(str(existing.with_suffix('.mp4')))
    view.container.setCurrentIndex(0)
    assert 'already exists' in window.model.state.form_error
    assert not view.run_button.isEnabled()
    assert existing.read_bytes() == b'keep' and source.read_bytes() == b'source'
    window.close()


def test_popup_content_geometry_tooltips_and_keyboard(app):
    window = QWidget()
    layout = QVBoxLayout(window)
    combo = ReadableComboBox()
    layout.addWidget(combo)
    combo.addItems(['Short', 'A substantially longer container and codec description'])
    combo.setFixedWidth(140)
    apply_theme(window)
    window.show()
    app.processEvents()
    combo.showPopup()
    app.processEvents()
    view = combo.view()
    assert view.isVisible()
    assert view.viewport().width() >= view.sizeHintForColumn(0)
    assert view.visualRect(combo.model().index(1, 0)).height() >= combo.fontMetrics().height()
    assert combo.itemData(1, Qt.ItemDataRole.ToolTipRole) == combo.itemText(1)
    assert combo.screen().availableGeometry().contains(view.window().geometry())
    QTest.keyClick(view, Qt.Key.Key_Down)
    QTest.keyClick(view, Qt.Key.Key_Return)
    assert combo.currentIndex() == 1
    combo.addItem('Very long dynamic label ' * 30)
    combo.showPopup()
    app.processEvents()
    assert combo.screen().availableGeometry().contains(view.window().geometry())
    assert combo.itemData(2, Qt.ItemDataRole.ToolTipRole) == combo.itemText(2)
    assert view.horizontalScrollBar().maximum() > 0
    combo.hidePopup()
    window.close()


@pytest.mark.parametrize('title', ['Convert', 'Compress'])
def test_encoding_manual_extension_and_collision_validation(app, tmp_path, title):
    from media_wrapper.application.conversion_service import conversion_plan
    from media_wrapper.application.operation_service import prepare_operation
    from media_wrapper.domain.operations import PlanValidationError
    from media_wrapper.ui.encoding_view import EncodingView

    source = tmp_path / 'source.mkv'
    source.write_bytes(b'source')
    media = MediaFile(source, streams=(MediaStream(0, 'video', 'h264'),))
    view = EncodingView(title)
    view.set_media(media, False)
    view._encoders[0].setCurrentText('copy')
    view.destination.setText(str(tmp_path / 'wrong.mp4'))
    with pytest.raises(PlanValidationError, match='must use .mkv'):
        prepare_operation(conversion_plan(media, view.request()))
    assert view.destination.text().endswith('wrong.mp4')
    view.destination.setText(str(source))
    with pytest.raises(PlanValidationError):
        prepare_operation(conversion_plan(media, view.request()))
    existing = tmp_path / 'exists.mp4'
    existing.write_bytes(b'keep')
    view.destination.setText(str(existing.with_suffix('.mkv')))
    view.container.setCurrentIndex(1)
    with pytest.raises(PlanValidationError):
        prepare_operation(conversion_plan(media, view.request()))
    assert existing.read_bytes() == b'keep'
    view.close()
