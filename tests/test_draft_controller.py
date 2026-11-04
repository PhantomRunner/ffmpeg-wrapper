import time

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from media_wrapper.domain.inspection import InspectionStatus
from media_wrapper.ui.draft_controller import DraftController


def wait(app, predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert predicate()


def test_async_import_probe_and_edit_while_queue_runs(sample, tmp_path):
    app = QApplication.instance() or QApplication([])
    binaries, plan = sample
    broken = tmp_path / 'broken.mkv'
    broken.write_text('not media')
    controller = DraftController()
    controller.binaries = binaries
    threads = []
    controller.changed.connect(lambda: threads.append(QThread.currentThread()))
    controller.import_sources((plan.media.path, broken))
    wait(app, lambda: not controller.busy)
    statuses = {i.path: i.inspection.status for i in controller.draft.items.values()}
    assert statuses == {plan.media.path: InspectionStatus.COMPLETED, broken: InspectionStatus.FAILED}
    assert threads and all(thread == app.thread() for thread in threads)
    controller.queue.running = True
    controller.patch('template', '{name}_changed')
    assert not controller.busy
    ready = next(i for i in controller.draft.items.values() if i.inspected)
    assert ready.options[controller.draft.operation].template == '{name}_changed'
    controller.queue.running = False
    controller.deleteLater()
    app.processEvents()


def test_file_change_after_probe_requires_explicit_reinspection(sample):
    from media_wrapper.application.draft_service import prepare_draft, snapshot_draft
    app = QApplication.instance() or QApplication([])
    controller = DraftController()
    controller.binaries = sample[0]
    source = sample[1].media.path
    controller.import_sources((source,))
    wait(app, lambda: not controller.busy)
    assert next(iter(controller.draft.items.values())).fingerprint
    with source.open('ab') as stream:
        stream.write(b'changed after probe')
    result = prepare_draft(snapshot_draft(controller.draft), controller.binaries)
    assert not result.ready
    assert result.items[0].validation.field == 'input'
    assert 'Inspect it again' in result.items[0].validation.error
    controller.deleteLater()
    app.processEvents()


def test_import_requests_are_not_lost_during_discovery(sample, tmp_path, monkeypatch):
    from media_wrapper.ui import draft_controller
    app = QApplication.instance() or QApplication([])
    source = sample[1].media.path
    second = tmp_path / 'queued-import.wav'
    second.write_bytes(source.read_bytes())
    original = draft_controller.discover_sources
    def delayed(*args):
        time.sleep(.05)
        return original(*args)
    monkeypatch.setattr(draft_controller, 'discover_sources', delayed)
    controller = DraftController()
    controller.binaries = sample[0]
    controller.import_sources((source,))
    controller.import_sources((second,))
    wait(app, lambda: not controller.busy)
    assert {item.path for item in controller.draft.items.values()} == {source, second}
    assert all(item.inspected for item in controller.draft.items.values())
    controller.deleteLater()
    app.processEvents()
