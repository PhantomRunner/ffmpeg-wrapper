from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget

from media_wrapper.application.size_estimate import estimate_plan_size
from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.operations import (
    EncodingProfile,
    MediaOperation,
    OperationPlan,
    OutputTarget,
    StreamSelection,
)
from media_wrapper.domain.remux import Container
from media_wrapper.ui.main_window import MainWindow


def test_all_modes_have_no_timelines_and_queue_remains_available(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    window.show()
    for mode in range(6):
        window.navigation.setCurrentRow(mode)
        app.processEvents()
        assert window.queue_view.isVisible() == (mode == 4)
        assert window.workspace.horizontal.isVisible()
    assert not any('Timeline' in tabs.tabText(i) for tabs in window.findChildren(QTabWidget) for i in range(tabs.count()))
    assert not any(button.text() == 'Settings' for button in window.workspace.findChildren(QPushButton))
    assert window.workspace.library.property('role') == 'workspacePanel'
    assert window.workspace.inspector.property('role') == 'workspacePanel'
    assert window.workspace.horizontal.handleWidth() >= 10
    window.close()


def test_status_estimate_updates_with_operation_and_rates(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    source = tmp_path / 'input.mkv'
    source.touch()
    media = MediaFile(source, duration=60, size_bytes=20000000, streams=(MediaStream(0, 'video', 'h264'),))
    window.model.add_files([source])
    window.model._inspected(media)
    window.navigation.setCurrentRow(3)
    view = window.compress_view
    assert window.output_estimate.text() == 'Output: variable'
    view.mode.setCurrentText('bitrate')
    assert '14.6 MiB' in window.output_estimate.text()
    view.video_bitrate.setValue(4000)
    assert '29.2 MiB' in window.output_estimate.text()
    view.mode.setCurrentText('target')
    view.target_size.setValue(50)
    assert '50.0 MiB' in window.output_estimate.text()
    window.navigation.setCurrentRow(1)
    assert '19.5 MiB' in window.output_estimate.text()
    window.navigation.setCurrentRow(5)
    assert window.output_estimate.text() == 'Output: —'
    window.close()
    app.processEvents()


def test_estimates_do_not_invent_rates_for_partial_copy_or_quality():
    media = MediaFile(Path('/input.mkv'), size_bytes=20000000,
                      streams=(MediaStream(0, 'video', 'h264'), MediaStream(1, 'audio', 'aac')))
    plan = OperationPlan(MediaOperation.REMUX, media, (StreamSelection(0), StreamSelection(1)),
                         OutputTarget(Path('/output.mkv'), Container.MATROSKA))
    assert estimate_plan_size(plan) == 20400000
    assert estimate_plan_size(replace(plan, streams=(StreamSelection(0),))) is None
    quality = replace(plan, streams=(StreamSelection(0, EncodingProfile('libx264', crf=23)),))
    assert estimate_plan_size(quality) is None


def test_legacy_layout_drops_timeline_state(monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    settings = QSettings(str(tmp_path / 'old-layout.ini'), QSettings.Format.IniFormat)
    window = MainWindow()
    window.show()
    window.navigation.setCurrentRow(2)
    app.processEvents()
    saved = window.workspace.horizontal.saveState()
    window.close()
    settings.setValue('workspace/version', '2')
    settings.setValue('workspace/mode', 2)
    settings.setValue('workspace/modes/2/horizontal', saved)
    settings.setValue('workspace/modes/2/timeline', 1)
    restored = MainWindow(layout_settings=settings)
    restored.show()
    app.processEvents()
    assert restored.navigation.currentRow() == 2
    assert not hasattr(restored.workspace, 'timelines')
    restored.close()
    assert settings.value('workspace/version') == '3'
    assert not settings.contains('workspace/modes/2/timeline')
