"""Serialize terminal snapshots once; all history I/O runs through a worker."""
from PySide6.QtCore import QObject

from media_wrapper.domain.history_document import record_payload


class HistorySync(QObject):
    def __init__(self, controller, repository):
        super().__init__(controller)
        self.controller, self.repository = controller, repository
        self.seen, self.pending = set(), {}
        self.removals = []
        self.disabled = False
        self.loaded = False
        controller.queue.changed.connect(self.observe)
        controller.service('history', repository.read, self._loaded, self._failed)

    def _loaded(self, records):
        existing = {r.id for r in self.controller.queue.records}
        self.seen.update(r.id for r in records)
        self.controller.queue.records.extend(r for r in records if r.id not in existing)
        self.loaded = True
        self.controller.queue.changed.emit()
        self._drain()

    def _failed(self, error):
        self.disabled = True
        self.controller.notice.emit('History could not be saved/loaded; its original file is preserved. ' + error)

    def observe(self):
        if self.disabled:
            return
        eligible = set(self.controller.queue.finished_history_ids())
        for record in self.controller.queue.records:
            if record.id in eligible and record.id not in self.seen:
                self.pending[record.id] = record_payload(record)
                self.seen.add(record.id)
        self._drain()

    def clear(self, ids, callback):
        if self.disabled:
            self.controller.notice.emit('History storage is unavailable. Its existing records are preserved; repair it and restart before clearing.')
            return
        self.removals.append((tuple(ids), callback))
        self._drain()

    def _drain(self):
        if self.disabled or not self.loaded or 'history' in self.controller.calls:
            return
        if self.removals:
            ids, callback = self.removals.pop(0)
            for item_id in ids:
                self.pending.pop(item_id, None)
            def finished(_value):
                callback(ids)
                self._drain()
            self.controller.service('history', lambda: self.repository.merge(remove=ids), finished, self._failed)
        elif self.pending:
            entries = tuple(self.pending.values())
            self.pending.clear()
            self.controller.service('history', lambda: self.repository.merge(entries), lambda _value: self._drain(), self._failed)
