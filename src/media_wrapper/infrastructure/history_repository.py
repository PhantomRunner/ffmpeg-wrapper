"""Locked, atomic terminal history storage, separate from no-overwrite exports."""
import json

from media_wrapper.domain.history_document import history_entries, record_payload
from media_wrapper.infrastructure.document_lock import document_lock
from media_wrapper.infrastructure.json_documents import read_document
from media_wrapper.infrastructure.settings_repository import SettingsRepository

HISTORY_LIMIT = 32 * 1048576


class HistoryRepository:
    def __init__(self, path):
        self.path = path

    def _read(self):
        if not self.path.exists():
            return ()
        return history_entries(read_document(self.path, limit=HISTORY_LIMIT))

    def read(self):
        if not self.path.exists():
            return ()
        with document_lock(self.path):
            return self._read()

    def merge(self, entries=(), remove=()):
        """Under one lock, preserve concurrent records and remove only captured IDs."""
        with document_lock(self.path):
            merged = {r.id: record_payload(r) for r in self._read()}
            for entry in entries:
                merged[entry['id']] = entry
            for item_id in remove:
                merged.pop(item_id, None)
            payload = {'kind': 'media-wrapper-history', 'version': 1, 'records': list(merged.values())}
            history_entries(json.loads(json.dumps(payload)))
            if len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) > HISTORY_LIMIT:
                raise ValueError('History exceeds 32 MiB. Clear finished records before saving more history.')
            SettingsRepository(self.path).write(payload)
