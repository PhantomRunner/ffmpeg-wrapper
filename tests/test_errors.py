"""Application error contracts and reporting across worker boundaries."""
import json
import logging
import subprocess
from pathlib import Path

import pytest

from media_wrapper.application.binary_service import detect_binaries
from media_wrapper.application.errors import (
    ApplicationError,
    normalize_error,
    report_failure,
)
from media_wrapper.application.media_service import MediaService
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.ui.main_window import (
    DetectionWorker,
    InspectionWorker,
    RemuxPreparationWorker,
)


@pytest.mark.parametrize(('error', 'expected'), [
    (FileNotFoundError('missing'), 'required file was not found'),
    (PermissionError('denied'), 'Permission denied'),
    (subprocess.TimeoutExpired('ffprobe', 30), 'timed out'),
    (json.JSONDecodeError('bad JSON', '', 0), 'invalid metadata'),
    (ValueError('Destination already exists'), 'Destination already exists'),
    (RuntimeError('FFprobe failed (1)'), 'process failed'),
    (KeyError('private implementation detail'), 'unexpected error'),
])
def test_normalized_errors_are_actionable(error, expected):
    failure = normalize_error('Inspection', error)
    assert str(failure).startswith('Inspection failed.')
    assert expected in str(failure)
    assert failure.details
    if isinstance(error, KeyError):
        assert 'private implementation detail' not in str(failure)


def test_binary_service_preserves_cause(monkeypatch):
    cause = PermissionError('cannot execute selected ffmpeg')
    def fail(*args):
        raise cause
    monkeypatch.setattr('media_wrapper.application.binary_service.resolve', fail)
    with pytest.raises(ApplicationError, match='Permission denied') as raised:
        detect_binaries('external', None)
    assert raised.value.__cause__ is cause


def test_process_stderr_is_preserved_in_diagnostics():
    cause = subprocess.CalledProcessError(1, ['ffprobe'], stderr='adapter failure details')
    wrapped = RuntimeError('Cannot run selected binary')
    wrapped.__cause__ = cause
    failure = normalize_error('Binary detection', wrapped)
    assert 'adapter failure details' in failure.details
    assert 'adapter failure details' not in str(failure)


def test_inspect_service_translates_probe_failure(monkeypatch):
    cause = subprocess.TimeoutExpired(['ffprobe'], 30)
    def fail(*args):
        raise cause
    monkeypatch.setattr('media_wrapper.application.media_service.inspect_media', fail)
    service = MediaService(Binaries(Path('ffmpeg'), Path('ffprobe'), 'test'))
    with pytest.raises(ApplicationError, match='timed out') as raised:
        service.inspect(Path('clip.mkv'))
    assert raised.value.__cause__ is cause


def test_existing_application_error_is_not_wrapped_or_duplicated(caplog):
    error = ApplicationError('Choose a new destination.', 'technical detail')
    with caplog.at_level(logging.ERROR):
        message = report_failure('Remux', error)
    assert message == 'Choose a new destination.'
    assert len(caplog.records) == 1
    assert 'technical detail' in caplog.text
    assert caplog.records[0].exc_info[1] is error


@pytest.mark.parametrize('kind', ['detect', 'inspect', 'prepare'])
def test_worker_reports_unexpected_failure_once(kind, monkeypatch, caplog):
    def fail(*args):
        raise KeyError('unexpected adapter bug')
    service = MediaService(Binaries(Path('ffmpeg'), Path('ffprobe'), 'test'))
    if kind == 'detect':
        monkeypatch.setattr('media_wrapper.ui.main_window.detect_binaries', fail)
        worker = DetectionWorker('external', None)
    elif kind == 'inspect':
        monkeypatch.setattr(service, 'inspect', fail)
        worker = InspectionWorker(service, Path('clip.mkv'))
    else:
        monkeypatch.setattr(service, 'prepare_remux', fail)
        worker = RemuxPreparationWorker(service, Path('in.mkv'), Path('out.mkv'), Container.MATROSKA)
    failures, successes = [], []
    worker.failed.connect(failures.append)
    worker.finished.connect(successes.append)
    with caplog.at_level(logging.ERROR):
        worker.run()
    assert len(failures) == 1
    assert 'unexpected error' in failures[0]
    assert not successes
    assert len(caplog.records) == 1
    assert 'unexpected adapter bug' in caplog.text
