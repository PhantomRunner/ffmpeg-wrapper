"""Cross-platform lock shared by mutable local JSON stores; not used by exports."""
from contextlib import contextmanager

from PySide6.QtCore import QLockFile


@contextmanager
def document_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path) + '.lock')
    if not lock.tryLock(2000):
        raise OSError('The document is locked by another application instance. Try again after it finishes.')
    try:
        yield
    finally:
        lock.unlock()
