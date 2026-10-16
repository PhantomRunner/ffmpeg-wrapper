"""Portable path policy and asynchronous diagnostic persistence."""
import logging
import threading

import pytest
from PySide6.QtCore import QStandardPaths

from media_wrapper.infrastructure.app_paths import AppPaths, resolve_app_paths
from media_wrapper.infrastructure.diagnostics import configure_logging


def test_paths_use_qt_native_locations_without_creating_settings(tmp_path, monkeypatch):
    config, data = tmp_path/'config ü', tmp_path/'local data'
    locations = {
        QStandardPaths.StandardLocation.AppConfigLocation: str(config),
        QStandardPaths.StandardLocation.AppLocalDataLocation: str(data),
    }
    monkeypatch.setattr(QStandardPaths, 'writableLocation', locations.__getitem__)
    paths = resolve_app_paths()
    assert paths.settings_file == config/'settings.json'
    assert paths.log_file == data/'logs'/'media-wrapper.log'
    assert not config.exists()
    assert not data.exists()


def test_unavailable_native_path_is_explicit(monkeypatch):
    monkeypatch.setattr(QStandardPaths, 'writableLocation', lambda _: '')
    with pytest.raises(OSError, match='per-user'):
        resolve_app_paths()


def test_logs_append_and_flush_on_background_thread(tmp_path, monkeypatch):
    paths = AppPaths(tmp_path/'config', tmp_path/'data')
    logger = logging.getLogger('media_wrapper.test')
    emitting_threads = []
    for message in ('first ü diagnostic', 'second diagnostic'):
        session = configure_logging(paths)
        original_emit = session.sink.emit
        def capture(record, emit=original_emit):
            emitting_threads.append(threading.get_ident())
            emit(record)
        monkeypatch.setattr(session.sink, 'emit', capture)
        try:
            logger.error(message)
        finally:
            session.close()
    text = paths.log_file.read_text(encoding='utf-8')
    assert text.count('first ü diagnostic') == 1
    assert text.count('second diagnostic') == 1
    assert all(identity != threading.get_ident() for identity in emitting_threads)
    assert not paths.settings_file.exists()
    assert not any(isinstance(handler, logging.handlers.QueueHandler)
                   for handler in logging.getLogger('media_wrapper').handlers)


def test_logs_rotate_with_bounded_backups(tmp_path):
    paths = AppPaths(tmp_path/'config', tmp_path/'data')
    session = configure_logging(paths)
    session.sink.maxBytes = 200
    try:
        for number in range(20):
            session.logger.error('diagnostic %s %s', number, 'x' * 80)
    finally:
        session.close()
    files = list(paths.log_file.parent.iterdir())
    assert len(files) == 4  # active file plus three backups
    assert 'diagnostic 19' in paths.log_file.read_text(encoding='utf-8')


def test_log_directory_failure_keeps_console_diagnostics(tmp_path, capsys):
    blocker = tmp_path/'file-not-directory'
    blocker.write_text('keep')
    session = configure_logging(AppPaths(tmp_path/'config', blocker))
    try:
        assert session.log_file is None
        assert 'File logging unavailable' in session.status
        session.logger.error('failure remains visible')
    finally:
        session.close()
    assert 'failure remains visible' in capsys.readouterr().err
    assert blocker.read_text() == 'keep'


def test_path_resolution_failure_has_explicit_console_fallback(capsys):
    session = configure_logging(None, 'No native path')
    try:
        assert 'No native path' in session.status
    finally:
        session.close()
    assert 'No native path' in capsys.readouterr().err
