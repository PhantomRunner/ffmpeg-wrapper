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
    source.touch()
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


def test_multi_file_picker_and_selection(shell, tmp_path, monkeypatch):
    first, second = tmp_path/'a.wav', tmp_path/'b.wav'
    first.touch()
    second.touch()
    monkeypatch.setattr('media_wrapper.ui.main_window.QFileDialog.getOpenFileNames',
                        lambda *args: ([str(first), str(second)], ''))
    shell.choose_file()
    assert shell.files_view.file_list.count() == 2
    shell.model.state.source = first
    shell.files_view.file_list.setCurrentRow(1)
    assert shell.source is None
    assert shell.model.state.current_file == second
    shell.files_view.clear_button.click()
    assert shell.files_view.file_list.count() == 0
    assert not shell.remux_button.isEnabled()


def test_drop_accepts_local_files_and_rejects_remote_urls(shell, tmp_path):
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDropEvent
    source = tmp_path/'drop ü.wav'
    source.touch()
    for url, accepted in ((QUrl.fromLocalFile(str(source)), True), (QUrl('https://example.com/a.wav'), False)):
        mime = QMimeData()
        mime.setUrls([url])
        event = QDropEvent(QPointF(1, 1), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        shell.files_view.dropEvent(event)
        assert event.isAccepted() == accepted
    assert shell.model.state.files == (source,)


def test_recent_destination_is_used_for_next_dialog(shell, tmp_path, monkeypatch):
    shell.model.state.source = tmp_path/'input.wav'
    shell.model.state.recent_destination = tmp_path/'exports'
    seen = []
    def dialog(*args):
        seen.append(args[2])
        return '', ''
    monkeypatch.setattr('media_wrapper.ui.main_window.QFileDialog.getSaveFileName', dialog)
    shell.choose_remux_destination()
    assert Path(seen[0]).parent == tmp_path/'exports'


def test_form_validation_preview_and_execution_revalidation(shell, tmp_path, monkeypatch):
    import json

    from media_wrapper.application.media_service import MediaService
    from media_wrapper.domain.media import MediaInfo
    from media_wrapper.domain.remux import Container
    source, destination = tmp_path/'input.wav', tmp_path/'output.mkv'
    source.touch()
    monkeypatch.setattr(MediaService, 'inspect', lambda self, path:
                        MediaInfo(path, 'wav', 1, 1, ({'index': 0, 'codec_type': 'audio', 'codec_name': 'pcm_s16le'},)))
    shell.model.state.source = source
    shell.model.set_output(str(source), Container.MATROSKA)
    assert not shell.remux_button.isEnabled()
    assert 'differ' in shell.remux_view.validation.text()
    shell.model.set_output(str(destination), Container.MATROSKA)
    shell.remux_view.advanced_toggle.setChecked(True)
    shell.remux_view.preview_button.click()
    deadline = time.monotonic() + 5
    while shell.model.state.busy and time.monotonic() < deadline:
        QApplication.instance().processEvents()
        time.sleep(.001)
    assert not shell.model.state.busy
    assert shell.remux_view.preview.isReadOnly()
    command = json.loads(shell.remux_view.preview.toPlainText())
    assert command[-1] == str(destination)
    assert '-c' in command and 'copy' in command
    assert not destination.exists()
    # A file appearing after preview must still be protected when Run is pressed.
    destination.write_bytes(b'keep')
    shell.run_form()
    deadline = time.monotonic() + 5
    while shell.model.state.busy and time.monotonic() < deadline:
        QApplication.instance().processEvents()
        time.sleep(.001)
    assert destination.read_bytes() == b'keep'
    assert 'already exists' in shell.output.toPlainText()
    shell.remux_view.destination.setText(str(tmp_path/'different.mp4'))
    assert not shell.remux_view.preview.toPlainText()
    assert not shell.remux_button.isEnabled()
    assert '.mkv' in shell.remux_view.validation.text()


def test_preferences_restore_and_save_across_windows(tmp_path, monkeypatch):
    from media_wrapper.application.settings_service import SettingsService
    from media_wrapper.domain.preferences import Preferences
    from media_wrapper.infrastructure.settings_repository import SettingsRepository
    application = QApplication.instance() or QApplication([])
    path = tmp_path/'config'/'settings.json'
    service = SettingsService(SettingsRepository(path))
    service.load()
    assert service.save(Preferences(binary_mode='bundled', binary_directory=str(tmp_path/'bin'),
                                    recent_destination=str(tmp_path/'exports'), container='mp4',
                                    advanced=True, page=1, width=1000, height=700)) is None
    seen = []
    def detect(mode, directory):
        seen.append((mode, directory))
        return Binaries(Path('ffmpeg'), Path('ffprobe'), 'test')
    monkeypatch.setattr('media_wrapper.ui.workers.detect_binaries', detect)
    for iteration in range(2):
        window = MainWindow(settings_service=SettingsService(SettingsRepository(path)))
        deadline = time.monotonic() + 5
        while window.model.state.busy and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(.001)
        try:
            assert not window.model.state.busy
            assert window.pages.currentIndex() == (1 if iteration == 0 else 5)
            assert window.container.currentIndex() == 1
            assert window.remux_view.advanced_toggle.isChecked()
            assert window.model.state.recent_destination == tmp_path/'exports'
            assert window.model.state.files == ()
            window.navigation.setCurrentRow(5)
        finally:
            window.close()
    assert seen == [('bundled', str(tmp_path/'bin'))] * 2


def test_changed_binary_selection_requires_redetection(shell):
    shell.model.state.source = Path('already-inspected.wav')
    shell.folder.setText('/different/bin')
    assert shell.binaries is None
    assert shell.source is None
    assert not shell.remux_button.isEnabled()
    assert 'Click Detect' in shell.status.text()
