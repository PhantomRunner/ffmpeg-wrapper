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
