"""GUI-thread draft coordinator; services and queue execution have separate lifetimes."""
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

from PySide6.QtCore import (
    QFileSystemWatcher,
    QObject,
    Qt,
    QThread,
    Signal,
    Slot,
)

from media_wrapper.application.import_service import discover_sources
from media_wrapper.application.task_queue import TaskQueue
from media_wrapper.domain.draft import DraftState
from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
from media_wrapper.ui.workers import (
    DetectionWorker,
    DraftInspectionWorker,
    ServiceWorker,
)


class BackgroundCall(QObject):
    done = Signal(str, bool, object)
    progress = Signal(int, object)
    delivery_ready = Signal()

    def __init__(self, role, worker, parent=None, generation=0):
        super().__init__(parent)
        self.role, self.worker = role, worker
        self.generation = generation
        self.owner_thread = QThread.currentThread()
        self.thread = QThread(self)
        self.reply = None
        self.delivery_ready.connect(self._deliver, Qt.ConnectionType.QueuedConnection)
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        # Python QObject destruction in a worker can invert the Qt connection
        # mutex/GIL order against GUI accessibility work on PySide6 6.7.
        worker.finished.connect(self._return_worker, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(self._return_worker, Qt.ConnectionType.DirectConnection)
        worker.finished.connect(self._success, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._failure, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self.thread.quit, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self.thread.quit, Qt.ConnectionType.QueuedConnection)
        self.thread.finished.connect(self._cleaned, Qt.ConnectionType.QueuedConnection)
        if hasattr(worker, 'progress'):
            worker.progress.connect(self._progress, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def _progress(self, value):
        self.progress.emit(self.generation, value)

    @Slot()
    def _return_worker(self):
        # Called in the worker's owning thread, the only thread allowed to push
        # its affinity back. Keep it alive until run() and the thread have ended.
        self.worker.moveToThread(self.owner_thread)

    @Slot(object)
    def _success(self, result):
        self.reply = True, result

    @Slot(str)
    def _failure(self, error):
        self.reply = False, error

    @Slot()
    def _cleaned(self):
        self.worker.deleteLater()
        # Leave finished-signal dispatch before callbacks can start another call.
        # Retain both wrappers until deferred deletion, including on Qt 6.7.
        self.delivery_ready.emit()

    @Slot()
    def _deliver(self):
        self.done.emit(self.role, *self.reply)
        # The finished QThread is our child and is deleted with this call.
        self.deleteLater()


class DraftController(QObject):
    changed = Signal()
    notice = Signal(str)
    prepared = Signal(object, str)
    binaries_ready = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.draft = DraftState()
        self.queue = TaskQueue(self)
        self.queue.changed.connect(self._queue_changed)
        self.binaries = None
        self.capabilities = None
        self.status = 'Detect FFmpeg in Settings to inspect and process files.'
        self.calls = {}
        self.callbacks = {}
        self.import_cancel = Event()
        self.probe_cancel = Event()
        self.pending_probe = []
        self.pending_import = []
        self.generation = 0
        self.defaults = {}
        self.preparation = None
        self.prepared_reserved = ()
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
        call.done.connect(self._completed, Qt.ConnectionType.QueuedConnection)
        call.progress.connect(self._progress, Qt.ConnectionType.QueuedConnection)
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
            if role in ('detect', 'capabilities'):
                self.status = str(value)
            self.notice.emit(str(value))
            if on_error:
                on_error(str(value))
        if role == 'import' and self.pending_import:
            paths = tuple(self.pending_import)
            self.pending_import.clear()
            self.import_sources(paths)
        self.changed.emit()

    def detect(self, mode='external', directory=None):
        if 'detect' in self.calls:
            return
        self.generation += 1
        self.probe_cancel.set()
        self.binaries = self.capabilities = None
        self.draft.revision += 1
        self.status = 'Detecting FFmpeg and FFprobe…'
        generation = self.generation
        self.launch('detect', DetectionWorker(mode, directory), lambda binaries: self._detected(binaries, generation))

    def _detected(self, binaries, generation):
        if generation != self.generation:
            return
        self.binaries = binaries
        self.status = f'FFmpeg: {binaries.ffmpeg}\nFFprobe: {binaries.ffprobe}\n{binaries.version}'
        self.pending_probe.extend(item.path for item in self.draft.items.values() if not item.inspected)
        self._start_probe()
        self.binaries_ready.emit(binaries)

    def import_sources(self, paths):
        if 'import' in self.calls:
            self.pending_import.extend(paths)
            self.notice.emit('Additional import paths are queued; current discovery continues.')
            return
        self.import_cancel = Event()
        event = self.import_cancel
        self.service('import', lambda: discover_sources(tuple(paths), event), self._discovered)

    def _discovered(self, result):
        self.draft.add(result.paths)
        if not self.import_cancel.is_set():
            for path in result.paths:
                item = self.draft.items[self.draft._paths[path]]
                in_flight = bool(item.inspection and item.inspection.status in (InspectionStatus.PENDING, InspectionStatus.RUNNING)
                                 and 'probe' in self.calls)
                if not item.inspected and not in_flight:
                    self.pending_probe.append(path)
        if result.errors:
            self.notice.emit('\n'.join(result.errors))
        if not self.import_cancel.is_set():
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
        worker = DraftInspectionWorker(self.binaries, paths, self.probe_cancel)
        generation = self.generation
        for path in paths:
            self.draft.inspected(InspectionRecord(path, InspectionStatus.PENDING))
        self.launch('probe', worker, lambda results: self._probe_finished(generation, results))

    def _probe_finished(self, generation, results):
        if generation == self.generation:
            for record, fingerprint in results:
                self._accept_inspection(record, fingerprint)
        self._start_probe()

    @Slot(int, object)
    def _progress(self, generation, value):
        if generation == self.generation:
            record, fingerprint = value
            self._accept_inspection(record, fingerprint)
            self.changed.emit()

    def _accept_inspection(self, record, fingerprint=None):
        item_id = self.draft._paths.get(record.path)
        fresh = item_id is not None and not self.draft.items[item_id].options
        self.draft.inspected(record)
        if fingerprint and item_id in self.draft.items:
            self.draft.items[item_id].fingerprint = fingerprint
        if fresh and item_id in self.draft.items and self.draft.items[item_id].inspected:
            item = self.draft.items[item_id]
            for operation, options in item.options.items():
                item.options[operation] = replace(options,
                    request=replace(options.request, container=self.defaults.get('container', options.request.container)),
                    folder=self.defaults.get('folder', ''), template=self.defaults.get('template', options.template),
                    auto_number=self.defaults.get('auto_number', False))
            item.defaults = dict(item.options)

    def cancel_import(self):
        self.import_cancel.set()
        self.probe_cancel.set()
        self.pending_probe.clear()
        self.pending_import.clear()

    def patch(self, name, value, ids=None):
        self.draft.patch(name, value, ids)
        self.changed.emit()

    def include(self, item_id, included):
        if item_id in self.draft.items:
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
        if 'prepare' in self.calls:
            self.notice.emit('Validation is already running.')
            return
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
                     lambda result: self._prepared(result, action, generation, binaries, capabilities, reserved))

    def _prepared(self, result, action, generation, binaries, capabilities, reserved):
        if (result.snapshot.revision != self.draft.revision or generation != self.generation
                or binaries != self.binaries or capabilities is not self.capabilities
                or not set(self.reserved()) <= set(reserved)):
            self.notice.emit('The draft changed during validation. Validate the current settings again.')
            return
        self.preparation = result
        self.prepared_reserved = reserved
        paths = {str(i.source.path) for i in result.items if i.source.path.exists()}
        paths.update(str(i.validation.destination.parent) for i in result.items if i.validation.destination)
        if paths:
            self.watcher.addPaths(sorted(paths))
        self.prepared.emit(result, action)

    def enqueue_prepared(self, result, start=False):
        if result is not self.preparation or result.snapshot.revision != self.draft.revision:
            self.notice.emit('Validation is stale. Validate again before adding jobs.')
            return ()
        if not set(self.reserved()) <= set(self.prepared_reserved):
            self.notice.emit('The queue now reserves an output path. Validate again.')
            self.invalidate()
            return ()
        self.preparation = None
        records = self.queue.add_many(tuple(i.plan for i in result.ready), self.binaries,
                                      fingerprints={i.plan.media.path: i.fingerprint for i in result.ready})
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

    @Slot()
    def _queue_changed(self):
        if self.preparation and not set(self.reserved()) <= set(self.prepared_reserved):
            self.invalidate()
        else:
            self.changed.emit()
