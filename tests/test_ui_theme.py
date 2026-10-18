"""R2 presentation contracts; backend workflow regressions remain in the full suite."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

from media_wrapper.ui.theme import apply_theme, stylesheet
from media_wrapper.ui.theme.tokens import COLORS
from media_wrapper.ui.widgets.controls import (
    ActionButton,
    EmptyState,
    FieldRow,
    PanelHeader,
    StatusChip,
)


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_packaged_theme_resource_and_scoped_application(app):
    window, other = QWidget(), QWidget()
    before = app.styleSheet()
    apply_theme(window)
    assert window.styleSheet() == stylesheet() and other.styleSheet() == ''
    assert app.styleSheet() == before
    assert '$' not in stylesheet()
    assert 'check.svg' in stylesheet()
    for state in (':hover', ':focus', ':disabled', '[validation="error"]', '[state="loading"]'):
        assert state in stylesheet()
    window.close()
    other.close()


def test_controls_keep_keyboard_focus_names_and_state_text(app):
    window = QWidget()
    layout = QVBoxLayout(window)
    header = PanelHeader('Output', 'Choose a new destination.')
    field = QLineEdit()
    row = FieldRow('&Destination', field)
    action = ActionButton('Add to queue', primary=True)
    chip = StatusChip('Preparing', 'loading')
    for widget in (header, row, action, chip, EmptyState('No files', 'Import local media.')):
        layout.addWidget(widget)
    apply_theme(window)
    window.show()
    window.activateWindow()
    field.setFocus()
    app.processEvents()
    assert row.label.buddy() is field and field.accessibleName() == 'Destination'
    QTest.keyClick(field, Qt.Key.Key_Tab)
    assert action.hasFocus()
    clicked = []
    action.clicked.connect(lambda: clicked.append(True))
    QTest.keyClick(action, Qt.Key.Key_Space)
    assert clicked == [True]
    action.setEnabled(False)
    QTest.keyClick(action, Qt.Key.Key_Space)
    assert clicked == [True]
    for state, text in (('neutral', 'Pending'), ('success', 'Completed'), ('error', 'Failed'), ('loading', 'Working')):
        chip.set_status(text, state)
        assert text in chip.text() and chip.accessibleName() == text and chip.property('state') == state
    with pytest.raises(ValueError):
        chip.set_status('Bad state', 'unknown')
    window.close()


def luminance(color):
    values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
    return sum(v * coefficient for v, coefficient in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


@pytest.mark.parametrize('foreground,background', [('text', 'background'), ('text', 'panel'), ('text', 'control'),
                                                  ('secondary', 'panel'), ('secondary', 'control'),
                                                  ('on_accent', 'accent'), ('error', 'panel')])
def test_normal_text_token_contrast(foreground, background):
    light, dark = sorted([luminance(COLORS[foreground]), luminance(COLORS[background])], reverse=True)
    assert (light + 0.05) / (dark + 0.05) >= 4.5


def test_shell_theme_empty_and_busy_states(app, monkeypatch, tmp_path):
    from media_wrapper.domain.media import MediaFile, MediaStream
    from media_wrapper.ui.main_window import MainWindow
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    window.show()
    app.processEvents()
    assert not window.files_view.empty_state.isHidden()
    assert window.files_view.file_list.isHidden()
    assert not window.queue_view.empty_state.isHidden()
    assert window.activity.property('state') == 'neutral'
    source = tmp_path / 'source.wav'
    source.touch()
    window.model.add_files([source])
    assert window.files_view.empty_state.isHidden() and not window.files_view.file_list.isHidden()
    window.model._inspected(MediaFile(source, streams=(MediaStream(0, 'audio', 'pcm_s16le'),)))
    window.model.set_output(str(source), window.model.state.container)
    assert window.remux_view.destination.property('validation') == 'error'
    window.model.state.busy = True
    window.render()
    assert window.activity.property('state') == 'loading'
    assert not window.choose_file_button.isEnabled()
    window.model.state.busy = False
    window.close()
