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


def test_error_output_excludes_progress_and_exit_summary():
    app = QApplication.instance() or QApplication([])
    runner = ProcessRunner()
    results = []
    runner.finished.connect(lambda *r: results.append(r))
    message = 'Error opening output file: Permission denied'
    script = "import sys; print('frame=10\\nprogress=end'); print(sys.argv[1], file=sys.stderr); sys.exit(1)"
    runner.start([sys.executable, '-c', script, message])
    wait(app, lambda: bool(results))
    assert not results[0][0]
    assert runner.error_output.strip() == message
    assert 'FFmpeg exit code: 1' in results[0][1]
    assert 'frame=10' in results[0][1]


def test_stubborn_process_is_killed_after_cancel():
    import os

    import pytest
    if os.name == 'nt':
        pytest.skip('Windows terminate already force-stops; POSIX SIGTERM escalation check')
    app = QApplication.instance() or QApplication([])
    runner = ProcessRunner()
    results, output = [], []
    runner.finished.connect(lambda *r: results.append(r))
    runner.stdout.connect(output.append)
    runner.start([sys.executable, '-u', '-c', "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready'); time.sleep(60)"])
    wait(app, lambda: bool(output))
    runner.cancel()
    wait(app, lambda: bool(results))
    assert runner.cancelled and not results[0][0]
    assert not runner.kill_timer.isActive()
