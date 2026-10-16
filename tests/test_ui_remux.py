"""Offscreen smoke coverage for the asynchronous desktop operation lifecycle."""
import os
import subprocess
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from media_wrapper.application.remux_task import RemuxTask
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import resolve
from media_wrapper.infrastructure.ffmpeg.process_runner import ProcessRunner
from media_wrapper.ui.main_window import MainWindow


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, predicate):
    deadline = time.monotonic() + 15
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate(), 'Asynchronous operation did not complete'


def test_process_failed_to_start(app, tmp_path):
    runner = ProcessRunner()
    results = []
    runner.finished.connect(lambda success, message: results.append((success, message)))
    runner.start([str(tmp_path/'missing-executable')])
    wait_for(app, lambda: bool(results))
    assert len(results) == 1
    assert results[0][0] is False


def test_task_rechecks_destination(app, tmp_path):
    destination = tmp_path/'exists.mkv'
    destination.write_bytes(b'keep')
    task = RemuxTask()
    results = []
    task.finished.connect(lambda success, message: results.append((success, message)))
    task.start(['unused', str(destination)])
    assert results[0][0] is False
    assert destination.read_bytes() == b'keep'


def test_window_inspect_and_remux(app, tmp_path):
    try:
        binaries = resolve()
    except (FileNotFoundError, RuntimeError) as exc:
        pytest.skip(str(exc))
    source, destination = tmp_path/'source clip.wav', tmp_path/'output ü clip.mkv'
    subprocess.run([str(binaries.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i',
                    'sine=duration=0.1', '-n', str(source)], check=True, capture_output=True, timeout=15)
    window = MainWindow()
    window.show()
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(1)
    try:
        wait_for(app, lambda: window.thread is None)
        assert window.binaries is not None
        window.run_inspection(source)
        wait_for(app, lambda: window.thread is None)
        assert window.remux_button.isEnabled()
        assert 'Container: wav' in window.output.toPlainText()
        window.run_remux(destination, Container.MATROSKA)
        wait_for(app, lambda: window.thread is None and window.remux_task is None)
        assert 'Remux complete.' in window.output.toPlainText()
        assert destination.is_file()
        assert window.choose_file_button.isEnabled()
        assert ticks
        original = destination.read_bytes()
        window.run_remux(destination, Container.MATROSKA)
        wait_for(app, lambda: window.thread is None)
        assert 'already exists' in window.output.toPlainText()
        assert destination.read_bytes() == original
    finally:
        timer.stop()
        wait_for(app, lambda: window.thread is None and window.remux_task is None)
        window.close()
