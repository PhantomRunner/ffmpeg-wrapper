import time

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from media_wrapper.domain.draft import EditScope
from media_wrapper.domain.operations import MediaOperation
from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.ui.flat_main_window import MainWindow


def wait(app, predicate, seconds=20):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert predicate()


@pytest.fixture
def flat_window(sample, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, 'detect', lambda self: None)
    settings = QSettings(str(tmp_path / 'layout.ini'), QSettings.Format.IniFormat)
    window = MainWindow(layout_settings=settings)
    window.controller.binaries = sample[0]
    window.show()
    app.processEvents()
    yield app, window
    window.controller.cancel_import()
    window.controller.queue.cancel_all()
    wait(app, lambda: not window.controller.busy and not window.controller.queue.running)
    window.close()
    app.processEvents()


def test_real_three_operations_use_queue_and_allow_future_draft_edit(flat_window, sample):
    app, window = flat_window
    controller = window.controller
    controller.import_sources((sample[1].media.path,))
    wait(app, lambda: not controller.busy)
    for count, operation in enumerate((MediaOperation.REMUX, MediaOperation.CONVERT, MediaOperation.COMPRESS), 1):
        window.set_operation(operation)
        controller.prepare('start')
        wait(app, lambda count=count: len(controller.queue.records) == count and not controller.busy and not controller.queue.running)
        record = controller.queue.records[-1]
        assert record.status == TaskStatus.COMPLETED, record.error
        assert record.result.path.is_file()
        assert record.plan.operation == operation
    frozen = controller.queue.records[-1].plan
    controller.patch('audio_bitrate', 192000)
    assert controller.queue.records[-1].plan == frozen
    assert window.shell.page == 'queue'
    assert not window.toolbar.add_files.isVisible()
    assert 'ETA' not in ' '.join(window.queue_page.model.HEADERS)
    assert not any('playback' in child.objectName().lower() for child in window.findChildren(type(window.sources)))


def test_scope_does_not_follow_table_selection_and_pages_hide_workspace_actions(flat_window, sample):
    app, window = flat_window
    window.controller.import_sources((sample[1].media.path,))
    wait(app, lambda: not window.controller.busy)
    window.render()
    window.sources.table.selectRow(0)
    app.processEvents()
    assert window.draft.scope is EditScope.INCLUDED
    assert len(window.draft.selected) == 1
    assert window.inspector.tracks.rowCount() == 1
    for route in ('settings', 'queue'):
        window.shell.set_page(route)
        assert not window.toolbar.add_files.isVisible()
        assert not window.start.isVisible()


def test_settings_change_during_preparation_cannot_enqueue(flat_window, sample, monkeypatch):
    from media_wrapper.application import draft_service
    app, window = flat_window
    controller = window.controller
    controller.import_sources((sample[1].media.path,))
    wait(app, lambda: not controller.busy)
    original = draft_service.prepare_draft
    def delayed(*args, **kwargs):
        time.sleep(.05)
        return original(*args, **kwargs)
    monkeypatch.setattr(draft_service, 'prepare_draft', delayed)
    controller.prepare('start')
    controller.patch('template', '{name}_later')
    wait(app, lambda: not controller.busy)
    assert not controller.queue.records
    assert controller.preparation is None
