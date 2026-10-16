import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from media_wrapper.infrastructure.ffmpeg.process_runner import ProcessRunner


def wait(app, predicate):
    deadline = time.monotonic() + 8
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.001)
    assert predicate()


def test_cancel_and_channels_keep_event_loop_alive():
    app = QApplication.instance() or QApplication([])
    runner = ProcessRunner()
    results, output, ticks = [], [], []
    runner.finished.connect(lambda *r: results.append(r))
    runner.stdout.connect(output.append)
    runner.start([sys.executable, '-u', '-c', "import sys,time; print('ready'); print('detail',file=sys.stderr); time.sleep(60)"])
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(1)
    try:
        wait(app, lambda: bool(output))
        runner.cancel()
        wait(app, lambda: bool(results))
        assert len(results) == 1 and not results[0][0]
        assert runner.cancelled and ticks
        assert 'detail' in results[0][1]
    finally:
        timer.stop()
        runner.cancel()


def test_crash_reports_once():
    app = QApplication.instance() or QApplication([])
    runner = ProcessRunner()
    results = []
    runner.finished.connect(lambda *r: results.append(r))
    runner.start([sys.executable, '-c', 'import os; os.abort()'])
    wait(app, lambda: bool(results))
    assert len(results) == 1 and not results[0][0]
