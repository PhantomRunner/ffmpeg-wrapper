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
    deadline = time.monotonic() + 5
    while window.model.state.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.001)
    window.close()


def test_navigation_preserves_inspection_and_enabled_state(shell):
    shell.output.setPlainText('Existing inspection')
    for index in range(6):
        shell.navigation.setCurrentRow(index)
        assert shell.pages.currentIndex() == index
        assert shell.output.toPlainText() == 'Existing inspection'
        assert shell.choose_file_button.isEnabled()
    assert shell.files_view.parentWidget() is not None
    assert shell.pages.widget(0).isAncestorOf(shell.files_view.stream_table)
    assert shell.pages.widget(1).isAncestorOf(shell.remux_view)
    assert shell.pages.widget(5).widget() is shell.settings_view


def test_busy_model_rejects_overlapping_operations(shell, monkeypatch, tmp_path):
    import threading

    from media_wrapper.application.media_service import MediaService
    from media_wrapper.domain.media import MediaFile
    from media_wrapper.domain.remux import Container
    entered, release = threading.Event(), threading.Event()
    def inspect(service, path, cancel_event=None):
        entered.set()
        release.wait(5)
        return MediaFile(path, 'wav', 1, 1, ())
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
    assert shell.choose_file_button.isEnabled()
    assert not shell.remux_button.isEnabled()  # Empty media cannot be remuxed.


def test_multi_file_picker_and_selection(shell, tmp_path, monkeypatch):
    first, second = tmp_path/'a.wav', tmp_path/'b.wav'
    first.touch()
    second.touch()
    monkeypatch.setattr('media_wrapper.ui.main_window.QFileDialog.getOpenFileNames',
                        lambda *args: ([str(first), str(second)], ''))
    from media_wrapper.domain.media import MediaFile
    monkeypatch.setattr('media_wrapper.application.media_service.MediaService.inspect',
                        lambda self, path, *args, **kwargs: MediaFile(path))
    shell.choose_file()
    deadline = time.monotonic() + 5
    while shell.model.state.busy and time.monotonic() < deadline:
        QApplication.instance().processEvents()
        time.sleep(.001)
    assert not shell.model.state.busy
    assert shell.files_view.file_list.model().rowCount() == 2
    shell.model.state.source = first
    shell.files_view.file_list.setCurrentIndex(shell.files_view.media_model.index(1))
    assert shell.source == second
    assert shell.model.state.current_file == second
    shell.files_view.clear_button.click()
    assert shell.files_view.file_list.model().rowCount() == 0
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
    from media_wrapper.domain.media import MediaFile, MediaStream
    from media_wrapper.domain.remux import Container
    source, destination = tmp_path/'input.wav', tmp_path/'output.mkv'
    source.touch()
    monkeypatch.setattr(MediaService, 'inspect', lambda self, path, cancel_event=None:
                        MediaFile(path, 'wav', 1, 1, (MediaStream(0, 'audio', 'pcm_s16le'),)))
    shell.model._inspected(MediaService(shell.binaries).inspect(source))
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
    validation = shell.validation_previews[shell.remux_view]
    assert validation.commands.isReadOnly()
    assert validation.report.files[0].ready
    command = json.loads(validation.commands.toPlainText())[0]
    assert Path(command[-1]).parent == destination.parent
    assert command[-1].endswith('.partial.mkv')
    assert '-map' in command and 'copy' in command
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


def test_stream_table_uses_real_indices_and_updates_selection(shell):
    from PySide6.QtCore import Qt

    from media_wrapper.domain.media import MediaFile, MediaStream
    shell.model._inspected(MediaFile(Path('fixture.mkv'), streams=(MediaStream(3, 'audio', 'aac'), MediaStream(8, 'subtitle', 'subrip'))))
    table = shell.files_view.stream_table
    assert table.item(0, 1).text() == '3'
    assert table.item(1, 1).text() == '8'
    table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    assert shell.model.state.selected_streams == (8,)


def test_selected_batch_cancellation_and_restart(shell, tmp_path, monkeypatch):
    import threading

    from media_wrapper.application.media_service import MediaService
    from media_wrapper.domain.inspection import InspectionStatus as Status
    from media_wrapper.domain.inspection import OperationCancelled
    from media_wrapper.domain.media import MediaFile, MediaStream
    files = tuple(tmp_path/name for name in ('first.wav', 'second.wav', 'third.wav'))
    for path in files:
        path.touch()
    entered = threading.Event()
    calls = []
    def inspect(service, path, cancel_event=None):
        calls.append(path)
        if path == files[1]:
            entered.set()
            assert cancel_event.wait(5)
            raise OperationCancelled()
        return MediaFile(path, 'wav', 1, 1, (MediaStream(4, 'audio', 'pcm_s16le'),))
    monkeypatch.setattr(MediaService, 'inspect', inspect)
    shell.model.add_files(list(files))
    shell.files_view.file_list.selectAll()
    shell.inspect_selected()
    try:
        assert entered.wait(3)
        QApplication.instance().processEvents()
        assert shell.files_view.cancel_button.isEnabled()
        shell.navigation.setCurrentRow(1)
        assert shell.pages.currentIndex() == 1
        shell.files_view.cancel_button.click()
        assert shell.model.state.cancel_requested
        deadline = time.monotonic()+5
        while shell.model.state.busy and time.monotonic()<deadline:
            QApplication.instance().processEvents()
            time.sleep(.001)
        assert not shell.model.state.busy
        assert [shell.model.state.inspections[p].status for p in files] == [Status.COMPLETED, Status.CANCELLED, Status.CANCELLED]
        assert calls == list(files[:2])
        assert shell.source == files[0]
        assert shell.files_view.inspect_selected_button.isEnabled()
        shell.model.select_streams(())
        shell.model.select_file(files[1])
        assert shell.source is None
        assert 'Cancelled' in shell.output.toPlainText()
        shell.model.select_file(files[0])
        assert shell.model.state.selected_streams == ()
        shell.run_inspection(files[2])
        deadline = time.monotonic()+5
        while shell.model.state.busy and time.monotonic()<deadline:
            QApplication.instance().processEvents()
            time.sleep(.001)
        assert shell.model.state.inspections[files[2]].status == Status.COMPLETED
        assert shell.source == files[2]
    finally:
        shell.model.cancel_inspection()
        deadline = time.monotonic()+5
        while shell.model.state.busy and time.monotonic()<deadline:
            QApplication.instance().processEvents()
            time.sleep(.001)


def test_remux_track_selection_updates_inspection(shell, tmp_path):
    from PySide6.QtCore import Qt

    from media_wrapper.domain.media import MediaFile, MediaStream
    source = tmp_path/'selected.mkv'
    source.write_bytes(b'fixture')
    shell.model._inspected(MediaFile(source, streams=(MediaStream(3, 'audio', 'aac'), MediaStream(8, 'subtitle', 'subrip'))))
    assert shell.remux_view.tracks.count() == 2
    shell.remux_view.tracks.item(1).setCheckState(Qt.CheckState.Unchecked)
    assert shell.model.state.selected_streams == (3,)
    assert shell.files_view.stream_table.item(1, 0).checkState() == Qt.CheckState.Unchecked


def test_remux_incompatible_tracks_require_explicit_deselection(shell, tmp_path):
    from media_wrapper.domain.media import MediaFile, MediaStream
    from media_wrapper.domain.remux import Container
    source = tmp_path/'input.mkv'
    source.touch()
    shell.model._inspected(MediaFile(source, streams=(MediaStream(0, 'video', 'h264'), MediaStream(2, 'subtitle', 'subrip'))))
    shell.model.set_output(str(tmp_path/'out.mp4'), Container.MP4)
    assert 'Stream 2' in shell.remux_view.validation.text()
    assert not shell.remux_button.isEnabled()
    assert shell.model.state.selected_streams == (0, 2)
    shell.model.select_streams((0,))
    assert shell.remux_button.isEnabled()
    shell.model.select_streams(())
    assert 'at least one' in shell.remux_view.validation.text()


def test_queue_view_real_failure_and_completion(shell, sample):
    from test_operation_task import wait

    from media_wrapper.domain.tasks import TaskStatus
    binaries, plan = sample
    shell.model.state.binaries = binaries
    shell.model._inspected(plan.media)
    shell.model.set_output(str(plan.output.path), plan.output.container)
    shell.remux_view.enqueue_button.click()
    other = plan.output.path.with_name('queued second.mkv')
    shell.model.set_output(str(other), plan.output.container)
    shell.remux_view.enqueue_button.click()
    assert shell.queue_view.task_model.rowCount() == 2
    plan.output.path.write_bytes(b'collision')
    shell.navigation.setCurrentRow(4)
    shell.queue_view.start_button.click()
    assert shell.model.state.busy
    assert not shell.remux_button.isEnabled()
    wait(QApplication.instance(), lambda: not shell.model.state.busy)
    assert [r.status for r in shell.model.queue.records] == [TaskStatus.FAILED, TaskStatus.COMPLETED]
    assert plan.output.path.read_bytes() == b'collision'
    shell.queue_view.table.selectRow(0)
    assert shell.queue_view.retry_button.isEnabled()
    assert 'already exists' in shell.queue_view.details.toPlainText()
    shell.queue_view.table.selectRow(1)
    assert 'Verified output' in shell.queue_view.details.toPlainText()
    assert 'pcm_s16le' in shell.queue_view.details.toPlainText()
    assert not shell.queue_view.retry_button.isEnabled()


def test_queue_view_cancel_pending_and_retry(shell, sample):
    from media_wrapper.domain.tasks import TaskStatus
    binaries, plan = sample
    shell.model.state.binaries = binaries
    shell.model._inspected(plan.media)
    shell.model.set_output(str(plan.output.path), plan.output.container)
    shell.remux_view.enqueue_button.click()
    shell.queue_view.cancel_button.click()
    assert shell.model.queue.records[0].status == TaskStatus.CANCELLED
    shell.queue_view.retry_button.click()
    assert [r.status for r in shell.model.queue.records] == [TaskStatus.CANCELLED, TaskStatus.PENDING]
    assert shell.queue_view.start_button.isEnabled()


def test_convert_preview_and_queue_execution(shell, sample):
    from test_operation_task import wait

    from media_wrapper.domain.tasks import TaskStatus
    binaries, plan = sample
    shell.model.state.binaries = binaries
    shell.model._inspected(plan.media)
    shell.navigation.setCurrentRow(2)
    view = shell.convert_view
    view.destination.setText(str(plan.output.path))
    view.preview_button.click()
    wait(QApplication.instance(), lambda: not shell.model.state.busy)
    validation = shell.validation_previews[view]
    assert validation.report.files[0].ready
    assert 'aac' in validation.commands.toPlainText()
    view.run_button.click()
    wait(QApplication.instance(), lambda: not shell.model.state.busy)
    record = shell.model.queue.records[-1]
    assert record.status == TaskStatus.COMPLETED, record.error
    assert record.result.streams[0].codec == 'aac'
    assert shell.pages.currentIndex() == 4


def test_capability_scan_ui_and_binary_change(shell, monkeypatch):
    from test_operation_task import wait

    from media_wrapper.domain.capabilities import (
        BuildCapabilities,
        CapabilityReport,
        EncoderCapability,
        EncoderStatus,
    )
    report = CapabilityReport(BuildCapabilities(('test', 1, 1, 'v'), 'version text', 'config text',
                                                frozenset({'libx264','h264_nvenc'}), ('cuda',), ()),
                              (EncoderCapability('h264_nvenc', True, EncoderStatus.LISTED, 'Not tested'),))
    monkeypatch.setattr('media_wrapper.application.capability_service.scan_capabilities', lambda *a, **k: report)
    shell.navigation.setCurrentRow(5)
    shell.settings_view.scan_button.click()
    wait(QApplication.instance(), lambda: not shell.model.state.busy)
    assert 'Listed; not tested' in shell.settings_view.capabilities.toPlainText()
    assert shell.convert_view.gpu_encoder.count() == 1
    from dataclasses import replace
    shell.model._capabilities_ready(replace(report, gpu=(EncoderCapability('h264_nvenc', True, EncoderStatus.WORKING),)))
    assert shell.convert_view.gpu_encoder.findText('h264_nvenc') >= 0
    shell.model.binary_selection_changed()
    assert shell.model.capabilities is None and shell.convert_view.gpu_encoder.count() == 1


def test_capability_scan_can_cancel_without_ui_freeze(shell, monkeypatch):
    from threading import Event

    from test_operation_task import wait

    from media_wrapper.domain.inspection import OperationCancelled
    entered = Event()
    def scan(ffmpeg, event, **kwargs):
        entered.set()
        assert event.wait(5)
        raise OperationCancelled()
    monkeypatch.setattr('media_wrapper.application.capability_service.scan_capabilities', scan)
    shell.settings_view.scan_button.click()
    assert entered.wait(2)
    assert shell.settings_view.cancel_scan.isEnabled()
    shell.navigation.setCurrentRow(2)
    assert shell.pages.currentIndex() == 2
    shell.settings_view.cancel_scan.click()
    wait(QApplication.instance(), lambda: not shell.model.state.busy)
    assert shell.model.capabilities is None
    assert 'cancelled' in shell.output.toPlainText()
    assert shell.settings_view.scan_button.isEnabled()


def test_profile_buttons_batch_and_diagnostics(shell, sample, tmp_path, monkeypatch):
    import json

    from test_operation_task import wait

    from media_wrapper.domain.tasks import TaskStatus
    binaries, plan = sample
    shell.model.state.binaries = binaries
    shell.model.add_files([plan.media.path])
    shell.model._inspected(plan.media)
    app = QApplication.instance()
    profile = tmp_path / 'profile.json'
    monkeypatch.setattr('media_wrapper.ui.main_window.QFileDialog.getSaveFileName', lambda *a: (str(profile), ''))
    view = shell.compress_view
    view.custom_arguments.setText('-threads 2')
    view.export_profile_button.click()
    wait(app, lambda: not shell.model.state.busy)
    assert profile.is_file(), shell.output.toPlainText()
    view.custom_arguments.clear()
    monkeypatch.setattr('media_wrapper.ui.main_window.QFileDialog.getOpenFileName', lambda *a: (str(profile), ''))
    shell.convert_view.import_profile_button.click()
    wait(app, lambda: not shell.model.state.busy)
    assert shell.pages.currentIndex() == 3
    assert view.custom_arguments.text() == '-threads 2'
    shell.files_view.file_list.selectAll()
    view.batch_template.setText('{stem}_{index}_batch{ext}')
    view.batch_button.click()
    wait(app, lambda: not shell.model.state.busy)
    assert len(shell.model.queue.records) == 1, shell.output.toPlainText()
    assert shell.model.queue.records[0].status == TaskStatus.PENDING
    queue_path = tmp_path / 'queue.json'
    monkeypatch.setattr('media_wrapper.ui.main_window.QFileDialog.getSaveFileName', lambda *a: (str(queue_path), ''))
    shell.queue_view.save_definitions.click()
    wait(app, lambda: not shell.model.state.busy)
    assert queue_path.is_file(), shell.output.toPlainText()
    diagnostics = tmp_path / 'diagnostics.json'
    monkeypatch.setattr('media_wrapper.ui.main_window.QFileDialog.getSaveFileName', lambda *a: (str(diagnostics), ''))
    assert not shell.settings_view.private_diagnostics.isChecked()
    shell.settings_view.export_diagnostics.click()
    wait(app, lambda: not shell.model.state.busy)
    assert not json.loads(diagnostics.read_text())['includes_private_details']
    assert str(plan.media.path) not in diagnostics.read_text()
    shell.settings_view.log_level.setCurrentText('ERROR')
    assert shell.preferences().log_level == 'ERROR'
    shell.settings_view.log_level.setCurrentText('INFO')


def test_active_binary_paths_and_explicit_sidecar_control(shell, tmp_path, monkeypatch):
    from test_operation_task import wait

    from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
    selected = tmp_path / 'sidecar ü' / 'bin'
    monkeypatch.setattr('media_wrapper.infrastructure.ffmpeg.binary_resolver.sidecar_directory', lambda: selected)
    shell.model._detected(Binaries(tmp_path / 'ffmpeg', tmp_path / 'ffprobe', 'FFmpeg version A | FFprobe version B'))
    assert str(tmp_path / 'ffmpeg') in shell.settings_view.status.text()
    assert str(tmp_path / 'ffprobe') in shell.settings_view.status.text()
    shell.settings_view.sidecar_button.click()
    wait(QApplication.instance(), lambda: not shell.model.state.busy)
    assert shell.mode.currentText() == 'bundled' and shell.folder.text() == str(selected)
