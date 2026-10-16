"""Navigation and shell interaction tests."""
import os
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.ui.main_window import MainWindow


@pytest.fixture
def shell(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('media_wrapper.ui.main_window.detect_binaries',
                        lambda *args: Binaries(Path('ffmpeg'), Path('ffprobe'), 'test'))
    window = MainWindow()
    deadline = time.monotonic() + 5
    while window.thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.001)
    assert window.thread is None
    yield window
    window.close()


def test_navigation_preserves_inspection_and_enabled_state(shell):
    shell.output.setPlainText('Existing inspection')
    for index in range(6):
        shell.navigation.setCurrentRow(index)
        assert shell.pages.currentIndex() == index
        assert shell.output.toPlainText() == 'Existing inspection'
        assert shell.choose_file_button.isEnabled()
    assert shell.pages.widget(0) is shell.files_view
    assert shell.pages.widget(1) is shell.remux_view
    assert shell.pages.widget(5) is shell.settings_view
