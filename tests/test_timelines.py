"""Real metadata/progress semantics; no fabricated timing or percentages."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    StreamSelection,
)
from media_wrapper.domain.progress import Progress
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.ui.models.tasks import TaskModel
from media_wrapper.ui.panels.media_timeline import MediaTimeline


def test_processing_unknown_progress_and_stable_selection():
    media = MediaFile(Path('source.wav'), streams=(MediaStream(0, 'audio', 'pcm_s16le'),))
    record = TaskRecord(OperationPlan(MediaOperation.REMUX, media, (StreamSelection(0),), OutputTarget(Path('out.mkv'), Container.MATROSKA)))
    model = TaskModel()
    model.update([record])
    assert model.data(model.index(0, 3), Qt.ItemDataRole.UserRole) is None
    assert 'Unknown' in model.data(model.index(0, 3))
    resets = []
    model.modelReset.connect(lambda: resets.append(True))
    record.progress = Progress(percent=37.5, speed=2.5, eta=12)
    record.status = TaskStatus.RUNNING
    model.update([record])
    assert not resets
    assert model.data(model.index(0, 3)) == '37.5%'
    assert model.data(model.index(0, 4)) == '2.50× / 12 s'
    assert model.data(model.index(0, 2)) == 'Running'


def test_media_tracks_unknown_duration_and_selection():
    app = QApplication.instance() or QApplication([])
    panel = MediaTimeline()
    streams = (MediaStream(2, 'video', 'h264'), MediaStream(7, 'audio', 'aac'), MediaStream(9, 'subtitle', 'srt'))
    media = MediaFile(Path('clip.mkv'), duration=12.5, streams=streams)
    panel.set_media(media)
    assert panel.lanes.count() == 3
    selected = []
    panel.stream_selected.connect(selected.append)
    panel.lanes.setCurrentRow(1)
    assert selected == [streams[1]]
    assert 'container duration' in panel.summary.text()
    assert len([item for item in panel.scene.items() if item.data(0) is not None]) == 3
    panel.set_media(MediaFile(Path('unknown.mkv'), streams=streams))
    assert 'Duration unknown' in panel.summary.text()
    assert not [item for item in panel.scene.items() if item.data(0) is not None]
    assert panel.lanes.count() == 3
    panel.set_media(None)
    assert panel.lanes.count() == 0 and not panel.scene.items()
    panel.close()
    app.processEvents()


def test_switch_preserves_queue_and_verified_output_action(monkeypatch, tmp_path):
    from media_wrapper.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    window = MainWindow()
    source = tmp_path / 'source.wav'
    source.touch()
    media = MediaFile(source, duration=3, streams=(MediaStream(0, 'audio', 'pcm_s16le'),))
    window.model.add_files([source])
    window.model._inspected(media)
    plan = OperationPlan(MediaOperation.REMUX, media, (StreamSelection(0),), OutputTarget(tmp_path / 'output.mkv', Container.MATROSKA))
    record = TaskRecord(plan)
    window.model.queue.records.append(record)
    window.render()
    assert not window.queue_view.open_output.isEnabled()
    for tab in (1, 0, 1):
        window.workspace.timelines.setCurrentIndex(tab)
        assert window.model.state.media is media
        assert window.model.queue.records == [record]
    record.status, record.result = TaskStatus.COMPLETED, media
    window.render_queue()
    opened = []
    monkeypatch.setattr('media_wrapper.ui.main_window.QDesktopServices.openUrl', opened.append)
    window.queue_view.open_output.click()
    assert opened[0].toLocalFile() == str(tmp_path)
    window.close()
    app.processEvents()
