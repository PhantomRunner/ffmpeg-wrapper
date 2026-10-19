from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from media_wrapper.ui.encoding_view import EncodingView
from media_wrapper.ui.parameter_help import HELP
from media_wrapper.ui.views import RemuxView


def test_primary_help_keyboard_and_screen_bounds():
    app = QApplication.instance() or QApplication([])
    view = EncodingView('Compress')
    view.resize(420, 600)
    view.show()
    app.processEvents()
    assert set(view.help_buttons) == set(HELP)
    button = view.help_buttons['container']
    assert button.accessibleName() == 'Help: Container'
    view.ensureWidgetVisible(button)
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    app.processEvents()
    assert view.help_dialog.isVisible()
    assert 'compatibility' in view.help_text.toPlainText()
    assert view.screen().availableGeometry().contains(view.help_dialog.frameGeometry())
    assert view.horizontalScrollBar().maximum() == 0
    view.help_dialog.close()
    view.activateWindow()
    view.container.setFocus()
    app.processEvents()
    QTest.keyClick(view.container, Qt.Key.Key_F1)
    app.processEvents()
    assert view.help_dialog.isVisible()
    view.help_dialog.close()
    view.close()


def test_remux_help_coverage():
    app = QApplication.instance() or QApplication([])
    view = RemuxView()
    assert set(view.help_buttons) == {'container', 'destination', 'tracks', 'metadata_policy', 'chapter_policy'}
    for name, button in view.help_buttons.items():
        assert button.accessibleName().startswith('Help:')
        assert getattr(view, name).toolTip()
    view.close()
    app.processEvents()
