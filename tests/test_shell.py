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
    monkeypatch.setattr('media_wrapper.ui.workers.detect_binaries',
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


def test_busy_model_rejects_overlapping_operations(shell, monkeypatch, tmp_path):
    import threading

    from media_wrapper.application.media_service import MediaService
    from media_wrapper.domain.media import MediaInfo
    from media_wrapper.domain.remux import Container
    entered, release = threading.Event(), threading.Event()
    def inspect(service, path):
        entered.set()
        release.wait(5)
        return MediaInfo(path, 'wav', 1, 1, ())
    monkeypatch.setattr(MediaService, 'inspect', inspect)
    source = tmp_path/'clip.wav'
    shell.run_inspection(source)
    try:
        assert entered.wait(2)
        assert shell.model.state.busy
        assert not shell.detect_button.isEnabled()
        shell.model.detect('bundled', 'ignored')
        shell.model.remux(tmp_path/'out.mkv', Container.MATROSKA)
        assert shell.model.state.binaries is not None
        shell.navigation.setCurrentRow(5)
        assert shell.pages.currentIndex() == 5
    finally:
        release.set()
        deadline = time.monotonic() + 5
        while shell.model.state.busy and time.monotonic() < deadline:
            QApplication.instance().processEvents()
            time.sleep(.001)
    assert shell.source == source
    assert shell.remux_button.isEnabled()
