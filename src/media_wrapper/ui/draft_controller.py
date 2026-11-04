"""GUI-thread draft coordinator; services and queue execution have separate lifetimes."""
from threading import Event
from types import SimpleNamespace

from PySide6.QtCore import QFileSystemWatcher, QObject, QThread, Signal, Slot

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
    prepared = Signal(object, str)

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
        self.preparation = None
        self.validation_cancel = Event()
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self.invalidate)
        self.watcher.directoryChanged.connect(self.invalidate)

    @property
    def busy(self):
        return bool(self.calls)

    @property
    def state(self):
        return SimpleNamespace(busy=self.busy or self.queue.running, binaries=self.binaries, status=self.status)

    def launch(self, role, worker, callback, on_error=None):
        if role in self.calls:
            self.notice.emit(f'{role.title()} is already running.')
            return False
        call = BackgroundCall(role, worker, self, self.generation)
        self.calls[role], self.callbacks[role] = call, (callback, on_error)
        call.done.connect(self._completed)
        call.progress.connect(self._progress)
        call.thread.start()
        self.changed.emit()
        return True

    def service(self, role, action, callback, on_error=None):
        return self.launch(role, ServiceWorker(action, role.title()), callback, on_error)

    @Slot(str, bool, object)
    def _completed(self, role, success, value):
        self.calls.pop(role, None)
        callback, on_error = self.callbacks.pop(role)
        if success:
            callback(value)
        else:
            self.status = str(value)
            self.notice.emit(str(value))
            if on_error:
                on_error(str(value))
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

    def reserved(self):
        from media_wrapper.domain.tasks import TaskStatus
        return tuple(r.plan.output.path for r in self.queue.records
                     if r.status in (TaskStatus.PENDING, TaskStatus.PREPARING, TaskStatus.RUNNING))

    def invalidate(self, *_):
        self.draft.revision += 1
        self.preparation = None
        paths = self.watcher.files() + self.watcher.directories()
        if paths:
            self.watcher.removePaths(paths)
        self.changed.emit()

    def prepare(self, action='validate'):
        from media_wrapper.application.draft_service import (
            prepare_draft,
            snapshot_draft,
        )
        if not self.binaries:
            self.notice.emit('Detect FFmpeg and FFprobe in Settings first.')
            return
        snapshot = snapshot_draft(self.draft)
        if not snapshot.inputs:
            self.notice.emit('Include at least one source file.')
            return
        generation, binaries, capabilities = self.generation, self.binaries, self.capabilities
        self.validation_cancel = Event()
        event, reserved = self.validation_cancel, self.reserved()
        self.service('prepare', lambda: prepare_draft(snapshot, binaries, capabilities, reserved, event),
                     lambda result: self._prepared(result, action, generation, binaries, capabilities))

    def _prepared(self, result, action, generation, binaries, capabilities):
        if (result.snapshot.revision != self.draft.revision or generation != self.generation
                or binaries != self.binaries or capabilities is not self.capabilities):
            self.notice.emit('The draft changed during validation. Validate the current settings again.')
            return
        self.preparation = result
        paths = {str(i.source.path) for i in result.items if i.source.path.exists()}
        paths.update(str(i.validation.destination.parent) for i in result.items if i.validation.destination)
        if paths:
            self.watcher.addPaths(sorted(paths))
        self.prepared.emit(result, action)

    def enqueue_prepared(self, result, start=False):
        from media_wrapper.application.batch_service import path_key
        if result is not self.preparation or result.snapshot.revision != self.draft.revision:
            self.notice.emit('Validation is stale. Validate again before adding jobs.')
            return ()
        protected = {path_key(p) for p in self.reserved()}
        if any(path_key(i.plan.output.path) in protected for i in result.ready):
            self.notice.emit('The queue now reserves an output path. Validate again.')
            self.invalidate()
            return ()
        records = self.queue.add_many(tuple(i.plan for i in result.ready), self.binaries)
        for record, item in zip(records, result.ready, strict=True):
            record.source_fingerprint = item.fingerprint
        for item in result.ready:
            if item.source.id in self.draft.items:
                self.draft.items[item.source.id].queued[result.snapshot.operation] = item.source.options
        self.preparation = None
        self.draft.revision += 1
        if start and records:
            self.queue.start()
        skipped = len(result.items) - len(records)
        self.notice.emit(f'Added {len(records)} job(s); {skipped} blocked file(s) remain in Workspace.')
        self.changed.emit()
        return records
