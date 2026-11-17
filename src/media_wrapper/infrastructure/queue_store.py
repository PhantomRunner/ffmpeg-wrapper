"""Single-owner local queue with a durable pre-publication journal."""
import json
import re
import sqlite3
import stat
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from PySide6.QtCore import QLockFile

from media_wrapper.domain.history_document import (
    media_payload,
    parse_media,
    parse_snapshot,
    snapshot_payload,
)
from media_wrapper.domain.tasks import TaskRecord, TaskStatus


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, allow_nan=False)


def _identity(path: Path) -> tuple[int, int, int, int] | None:
    info = path.stat(follow_symlinks=False)
    if not info.st_ino or not stat.S_ISREG(info.st_mode):
        return None
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class QueueStore:
    """Persist snapshots, never executable paths. Mutations are atomic in this database."""

    VERSION = 1

    def __init__(self, path: Path, log_dir: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = log_dir
        self._guard = RLock()
        self._owner = QLockFile(str(path) + '.lock')
        self._owner.setStaleLockTime(0)
        if not self._owner.tryLock(0):
            raise OSError('The processing queue is open in another application instance.')
        self._db = None
        try:
            self._db = sqlite3.connect(path, timeout=1.0, check_same_thread=False)
            self._db.execute('PRAGMA foreign_keys = ON')
            version = self._db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, self.VERSION):
                raise ValueError('Unsupported local queue schema; the original database is preserved.')
            if version == 0:
                self._db.executescript("""
                    BEGIN;
                    CREATE TABLE attempts (id TEXT PRIMARY KEY, position INTEGER NOT NULL, snapshot TEXT NOT NULL);
                    CREATE TABLE settings (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
                    CREATE TABLE publication (
                        attempt_id TEXT PRIMARY KEY REFERENCES attempts(id) ON DELETE CASCADE,
                        identity TEXT NOT NULL, verified TEXT NOT NULL
                    );
                    PRAGMA user_version = 1;
                    COMMIT;
                """)
        except (OSError, sqlite3.Error, ValueError):
            self.close()
            raise

    def close(self):
        with self._guard:
            if self._db is not None:
                self._db.close()
                self._db = None
            self._owner.unlock()

    def log_path(self, attempt_id: str) -> Path | None:
        return self.log_dir / f'{attempt_id}.log' if re.fullmatch('[a-f0-9]{32}', attempt_id) else None

    def option(self, key: str) -> bool:
        with self._guard:
            entry = self._db.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
            return bool(entry and entry[0])

    def set_option(self, key: str, value: bool) -> None:
        with self._guard, self._db:
            self._db.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', (key, int(value)))

    def _insert(self, records: tuple[TaskRecord, ...]) -> None:
        position = self._db.execute('SELECT COALESCE(MAX(position), -1) + 1 FROM attempts').fetchone()[0]
        self._db.executemany('INSERT INTO attempts VALUES (?, ?, ?)', (
            (record.id, position + offset, _json(snapshot_payload(record))) for offset, record in enumerate(records)
        ))

    def add(self, records: tuple[TaskRecord, ...]) -> None:
        with self._guard, self._db:
            self._insert(records)

    def move(self, first: str, second: str) -> None:
        with self._guard, self._db:
            rows = dict(self._db.execute('SELECT id, position FROM attempts WHERE id IN (?, ?)', (first, second)))
            self._db.executemany('UPDATE attempts SET position = ? WHERE id = ?', (
                (rows[second], first), (rows[first], second),
            ))

    def delete(self, ids: tuple[str, ...]) -> None:
        with self._guard, self._db:
            self._db.executemany('DELETE FROM attempts WHERE id = ?', ((attempt_id,) for attempt_id in ids))

    def _update(self, record: TaskRecord) -> None:
        self._db.execute('UPDATE attempts SET snapshot = ? WHERE id = ?', (_json(snapshot_payload(record)), record.id))

    def update(self, record: TaskRecord, *, terminal: bool = False) -> None:
        with self._guard, self._db:
            self._update(record)
            if terminal:
                self._db.execute('DELETE FROM publication WHERE attempt_id = ?', (record.id,))

    def before_publish(self, record: TaskRecord, staged: Path, final: Path, result) -> None:
        if staged != record.partial_path or final != record.plan.output.path:
            raise ValueError('Publication paths differ from the frozen job.')
        info = staged.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or not result.size_bytes or info.st_size != result.size_bytes:
            raise OSError('The staged file changed after verification.')
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) if info.st_ino else None
        with self._guard, self._db:
            self._update(record)
            self._db.execute('INSERT OR REPLACE INTO publication VALUES (?, ?, ?)', (
                record.id, _json(identity), _json(media_payload(replace(result, path=final))),
            ))

    def migrate(self, records: tuple[TaskRecord, ...]) -> tuple[TaskRecord, ...]:
        """Import old history once, so a later clear cannot resurrect deleted jobs."""
        with self._guard, self._db:
            if self.option('history_imported'):
                return ()
            existing = {row[0] for row in self._db.execute('SELECT id FROM attempts')}
            added = tuple(record for record in records if record.id not in existing)
            self._insert(added)
            self._db.execute('INSERT INTO settings VALUES (?, ?)', ('history_imported', 1))
            return added

    def restore(self) -> tuple[TaskRecord, ...]:
        with self._guard, self._db, closing(self._db.cursor()) as cursor:
            rows = cursor.execute("""
                SELECT snapshot, identity, verified FROM attempts
                LEFT JOIN publication ON publication.attempt_id = attempts.id ORDER BY position
            """).fetchall()
            records = []
            for snapshot, identity, verified in rows:
                record = parse_snapshot(json.loads(snapshot))
                record.log_path = self.log_path(record.id)
                if record.status in (TaskStatus.PREPARING, TaskStatus.RUNNING):
                    self._restore_log_tail(record)
                    self._recover_attempt(record, identity, verified)
                    self._update(record)
                    self._db.execute('DELETE FROM publication WHERE attempt_id = ?', (record.id,))
                records.append(record)
            return tuple(records)

    @staticmethod
    def _restore_log_tail(record):
        if record.log_path is None:
            return
        try:
            with record.log_path.open('rb') as stream:
                length = stream.seek(0, 2)
                stream.seek(max(0, length - 64000))
                record.log = stream.read().decode('utf-8', errors='replace')[-16000:]
        except OSError:
            pass

    def _recover_attempt(self, record, identity, verified):
        result = parse_media(json.loads(verified)) if verified is not None else None
        proof = json.loads(identity) if identity is not None else None
        if result is not None and result.path == record.plan.output.path and proof is not None:
            try:
                matches = _identity(result.path) == tuple(proof)
            except OSError:
                matches = False
            if matches:
                record.result = result
                record.status = TaskStatus.COMPLETED
                record.finished_at = datetime.now(UTC).isoformat()
                record.append_log('\nRecovered the verified output after interrupted publication.\n')
                return
        record.transition(TaskStatus.INTERRUPTED)
        record.error = 'The application closed before this attempt finished. Review its log or retry as a new attempt.'
        if record.partial_path is not None:
            record.error += f' Staged output may remain at {record.partial_path}.'
        record.append_log('\n' + record.error + '\n')
