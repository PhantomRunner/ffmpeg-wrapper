"""Shared selection and immutable validated enqueue contracts."""
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.ui.main_window import MainWindow
from media_wrapper.ui.models.media_files import MediaFileModel


def test_large_library_updates_status_without_reset(tmp_path):
    model = MediaFileModel()
    paths = tuple(tmp_path / f'{i} long source name.wav' for i in range(10000))
    model.update(paths, {})
    assert model.rowCount() == 10000
    assert model.data(model.index(9999), Qt.ItemDataRole.UserRole) == str(paths[-1])
    assert str(paths[-1]) in model.data(model.index(9999), Qt.ItemDataRole.ToolTipRole)
    resets = []
    model.modelReset.connect(lambda: resets.append(True))
    model.update(paths, {})
    assert not resets


def test_context_selection_and_validated_snapshot(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    source = tmp_path / 'source.wav'
    source.touch()
    window.model.state.binaries = Binaries(Path('ffmpeg'), Path('ffprobe'), 'test')
    window.model.add_files([source])
    media = MediaFile(source, streams=(MediaStream(0, 'audio', 'pcm_s16le'),))
    window.model._inspected(media)
    request = ConversionRequest(tmp_path / 'queued.mkv', Container.MATROSKA, ((0, 'copy'),))
    seen = []
    def validate(binaries, plan):
        seen.append(plan)
        return plan
    monkeypatch.setattr('media_wrapper.ui.view_model.validate_queue_snapshot', validate)
    window.model.encode(request, 'enqueue')
    window.convert_view.destination.setText(str(tmp_path / 'later.mkv'))
    deadline = time.monotonic() + 5
    while window.model.state.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.001)
    assert not window.model.state.busy
    assert len(seen) == len(window.model.queue.records) == 1
    assert window.model.queue.records[0].plan.output.path == request.destination
    assert window.convert_view._media is window.compress_view._media is media
    assert window.workspace.source.text() == str(source)
    window.close()


def test_snapshot_validation_rejects_existing_output(monkeypatch, tmp_path):
    import pytest

    from media_wrapper.application.conversion_service import (
        conversion_plan,
        validate_queue_snapshot,
    )
    source = tmp_path / 'source.wav'
    source.touch()
    output = tmp_path / 'output.mkv'
    output.write_bytes(b'keep')
    media = MediaFile(source, streams=(MediaStream(0, 'audio', 'pcm_s16le'),))
    monkeypatch.setattr('media_wrapper.application.conversion_service.MediaService.inspect', lambda *args: media)
    monkeypatch.setattr('media_wrapper.application.conversion_service.list_encoders', lambda *args: frozenset())
    plan = conversion_plan(media, ConversionRequest(output, Container.MATROSKA, ((0, 'copy'),)))
    with pytest.raises(ValueError):
        validate_queue_snapshot(Binaries(Path('ffmpeg'), Path('ffprobe'), 'test'), plan)
    assert output.read_bytes() == b'keep'
