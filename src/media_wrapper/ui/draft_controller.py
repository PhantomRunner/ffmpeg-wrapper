"""GUI-thread draft coordinator; services and queue execution have separate lifetimes."""
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal, Slot

from media_wrapper.application.import_service import discover_sources
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.task_queue import TaskQueue
from media_wrapper.domain.draft import DraftState
from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
from media_wrapper.ui.workers import DetectionWorker, InspectionWorker, ServiceWorker


class BackgroundCall(QObject):
    done = Signal(str, bool, object)
    progress = Signal(int, object)

    def __init__(self, role, worker, parent=None, generation=0):
        super().__init__(parent)
        self.role, self.worker = role, worker
        self.generation = generation
        self.thread = QThread(self)
        self.reply = None
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        worker.finished.connect(self._success)
        worker.failed.connect(self._failure)
        worker.finished.connect(self.thread.quit)
        worker.failed.connect(self.thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        self.thread.finished.connect(self._cleaned)
        if hasattr(worker, 'progress'):
            worker.progress.connect(self._progress)

    @Slot(object)
    def _progress(self, value):
        self.progress.emit(self.generation, value)

    @Slot(object)
    def _success(self, result):
        self.reply = True, result

    @Slot(str)
    def _failure(self, error):
        self.reply = False, error

    @Slot()
    def _cleaned(self):
        self.thread.deleteLater()
        self.thread, self.worker = None, None
        self.done.emit(self.role, *self.reply)
        self.deleteLater()


class DraftController(QObject):
    changed = Signal()
    notice = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.draft = DraftState()
        self.queue = TaskQueue(self)
        self.queue.changed.connect(self.changed)
        self.binaries = None
        self.capabilities = None
        self.status = 'Detect FFmpeg in Settings to inspect and process files.'
        self.calls = {}
        self.callbacks = {}
        self.import_cancel = Event()
        self.probe_cancel = Event()
        self.pending_probe = []
        self.generation = 0

    @property
    def busy(self):
        return bool(self.calls)

    def launch(self, role, worker, callback):
        if role in self.calls:
            self.notice.emit(f'{role.title()} is already running.')
            return False
        call = BackgroundCall(role, worker, self, self.generation)
        self.calls[role], self.callbacks[role] = call, callback
        call.done.connect(self._completed)
        call.progress.connect(self._progress)
        call.thread.start()
        self.changed.emit()
        return True

    def service(self, role, action, callback):
        return self.launch(role, ServiceWorker(action, role.title()), callback)

    @Slot(str, bool, object)
    def _completed(self, role, success, value):
        self.calls.pop(role, None)
        callback = self.callbacks.pop(role)
        if success:
            callback(value)
        else:
            self.status = str(value)
            self.notice.emit(str(value))
        self.changed.emit()

    def detect(self, mode='external', directory=None):
        if 'detect' in self.calls:
            return
        self.generation += 1
        self.probe_cancel.set()
        self.binaries = self.capabilities = None
        self.draft.revision += 1
        self.status = 'Detecting FFmpeg and FFprobe…'
        self.launch('detect', DetectionWorker(mode, directory), self._detected)

    def _detected(self, binaries):
        self.binaries = binaries
        self.status = f'FFmpeg: {binaries.ffmpeg}\nFFprobe: {binaries.ffprobe}\n{binaries.version}'
        self.pending_probe.extend(item.path for item in self.draft.items.values() if not item.inspected)
        self._start_probe()

    def import_sources(self, paths):
        self.import_cancel = Event()
        event = self.import_cancel
        self.service('import', lambda: discover_sources(tuple(paths), event), self._discovered)

    def _discovered(self, result):
        additions = self.draft.add(result.paths)
        self.pending_probe.extend(item.path for item in additions)
        if result.errors:
            self.notice.emit('\n'.join(result.errors))
        self._start_probe()

    def _start_probe(self):
        if 'probe' in self.calls or not self.pending_probe or not self.binaries:
            return
        paths = tuple(dict.fromkeys(self.pending_probe))
        self.pending_probe.clear()
        paths = tuple(p for p in paths if p in self.draft._paths)
        if not paths:
            return
        self.probe_cancel = Event()
        worker = InspectionWorker(MediaService(self.binaries), paths, self.probe_cancel)
        generation = self.generation
        for path in paths:
            self.draft.inspected(InspectionRecord(path, InspectionStatus.PENDING))
        self.launch('probe', worker, lambda results: self._probe_finished(generation, results))

    def _probe_finished(self, generation, results):
        if generation == self.generation:
            for record in results:
                self.draft.inspected(record)
        self._start_probe()

    @Slot(int, object)
    def _progress(self, generation, record):
        if generation == self.generation:
            self.draft.inspected(record)
            self.changed.emit()

    def cancel_import(self):
        self.import_cancel.set()
        self.probe_cancel.set()
        self.pending_probe.clear()

    def patch(self, name, value, ids=None):
        self.draft.patch(name, value, ids)
        self.changed.emit()

    def include(self, item_id, included):
        self.draft.include(item_id, included)
        self.changed.emit()
