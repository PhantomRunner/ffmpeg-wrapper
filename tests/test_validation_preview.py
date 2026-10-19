from pathlib import Path

from PySide6.QtWidgets import QApplication

from media_wrapper.application import validation_preview as service
from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    PlanValidationError,
    StreamSelection,
    ValidationCode,
)
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.ui.main_window import MainWindow


def candidate(tmp_path, name='clip'):
    source = tmp_path / (name + '.mkv')
    source.touch()
    plan = OperationPlan(MediaOperation.REMUX, MediaFile(source, streams=(MediaStream(0, 'video', 'h264'),)),
                         (StreamSelection(0),), OutputTarget(tmp_path / (name + '.mp4'), Container.MP4))
    return service.ValidationCandidate(source, plan.output.path, 'MP4', 'remux', lambda: plan)


def test_all_ready_and_mixed_reports(tmp_path, monkeypatch):
    a, b = candidate(tmp_path, 'a'), candidate(tmp_path, 'b')
    monkeypatch.setattr(service, 'preview_conversion', lambda binaries, plan: [['ffmpeg', '-n', str(plan.output.path)]])
    report = service.validate_candidates((a, b), None)
    assert report.summary == 'Ready: 2 · Warnings: 0 · Blocked: 0'
    assert all(file.commands and file.streams == ('Stream 0: copy',) for file in report.files)

    def preview(binaries, plan):
        if plan.media.path == b.source:
            raise PlanValidationError(ValidationCode.COMPATIBILITY, 'Stream 0 codec not supported in MP4')
        return [['ffmpeg']]
    monkeypatch.setattr(service, 'preview_conversion', preview)
    report = service.validate_candidates((a, b), None)
    assert report.summary == 'Ready: 1 · Warnings: 0 · Blocked: 1'
    assert 'Stream 0' in report.files[1].error
    assert 'compatible container' in report.files[1].advice
    assert not report.files[1].commands
    assert not a.destination.exists()


def test_collisions_block_all_affected_candidates(tmp_path, monkeypatch):
    from dataclasses import replace
    a, b = candidate(tmp_path, 'a'), candidate(tmp_path, 'b')
    b = replace(b, destination=a.destination)
    monkeypatch.setattr(service, 'preview_conversion', lambda *args: (_ for _ in ()).throw(AssertionError('Must not preview collisions')))
    report = service.validate_candidates((a, b), None)
    assert all(not file.ready and file.field == 'output' for file in report.files)
    report = service.validate_candidates((a,), None, (a.destination,))
    assert not report.files[0].ready


def test_widget_stale_results_and_blocked_actions(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    window.show()
    window.navigation.setCurrentRow(3)
    item = candidate(tmp_path)
    window.model.state.media = item.build_plan().media
    window.model.state.binaries = Binaries(Path('/ffmpeg'), Path('/ffprobe'), 'test')
    window.render()
    view = window.compress_view
    presenter = window.validation_previews[view]
    revision = presenter.begin()
    report = service.ValidationReport((service.blocked(item, PlanValidationError(
        ValidationCode.OUTPUT, 'Destination already exists')),))
    presenter.present(revision, report)
    assert 'Blocked: 1' in presenter.summary.text()
    assert not view.run_button.isEnabled() and not view.enqueue_button.isEnabled()
    assert 'Fix:' in presenter.results.toPlainText()
    assert presenter.commands.isReadOnly()
    assert presenter.results.accessibleName()
    view.container.setCurrentIndex(1)
    presenter.present(revision, report)
    assert presenter.report is None
    assert not presenter.details.isVisible()
    assert 'Not validated' in presenter.summary.text()
    window.close()
    app.processEvents()


def test_preview_callback_binds_request_not_current_operation(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    item = candidate(tmp_path)
    window.model.state.media = item.build_plan().media
    window.model.state.binaries = Binaries(Path('/ffmpeg'), Path('/ffprobe'), 'test')
    window.render()
    callbacks = []
    monkeypatch.setattr(window.model, 'validate_preview', lambda candidates, callback: callbacks.append(callback))
    window.validate_operation(window.convert_view)
    window.validate_operation(window.compress_view)
    report = service.ValidationReport((service.FileValidation(item.source, item.destination, 'MP4', 'convert'),))
    callbacks[0](report)
    assert window.validation_previews[window.convert_view].report == report
    assert window.validation_previews[window.compress_view].report is None
    window.convert_view.video_width.setValue(640)
    callbacks[0](report)
    assert window.validation_previews[window.convert_view].report is None
    window.close()
    app.processEvents()


def test_real_threaded_preview_and_external_path_invalidation(sample, monkeypatch):
    import time
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    binaries, plan = sample
    window = MainWindow()
    window.model.state.media = plan.media
    window.model.state.source = plan.media.path
    window.model.state.binaries = binaries
    window.model.state.selected_streams = (0,)
    window.model.state.destination = str(plan.output.path)
    window.render()
    from PySide6.QtCore import QThread
    delivered_threads = []
    presenter = window.validation_previews[window.remux_view]
    presenter.results.textChanged.connect(lambda: delivered_threads.append(QThread.currentThread()))
    window.validate_operation(window.remux_view)
    deadline = time.monotonic() + 10
    while window.model.thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    presenter = window.validation_previews[window.remux_view]
    assert window.model.thread is None
    assert presenter.report and presenter.report.files[0].ready
    assert 'Ready: 1' in presenter.summary.text()
    assert all(thread == app.thread() for thread in delivered_threads)
    assert not window.model.queue.records
    assert not plan.output.path.exists()
    plan.output.path.touch()
    deadline = time.monotonic() + 3
    while presenter.report is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert presenter.report is None
    window.validate_operation(window.remux_view)
    deadline = time.monotonic() + 10
    while window.model.thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert presenter.report and not presenter.report.files[0].ready
    assert not window.remux_view.run_button.isEnabled()
    window.close()
    app.processEvents()


def test_real_missing_encoder_and_warning_distinction(sample):
    from dataclasses import replace

    from media_wrapper.domain.operations import EncodingProfile
    binaries, plan = sample
    candidate = service.ValidationCandidate(plan.media.path, plan.output.path, 'Matroska', 'convert',
        lambda: replace(plan, operation=MediaOperation.CONVERT,
                        streams=(StreamSelection(0, EncodingProfile('nonexistent_encoder')),)))
    report = service.validate_candidates((candidate,), binaries)
    assert not report.files[0].ready
    assert 'Encoder' in report.files[0].error
    assert 'Settings' in report.files[0].advice
    candidate = replace(candidate, build_plan=lambda: replace(plan, hardware_note='CPU fallback selected'))
    report = service.validate_candidates((candidate,), binaries)
    assert report.files[0].ready
    assert report.summary == 'Ready: 1 · Warnings: 1 · Blocked: 0'
