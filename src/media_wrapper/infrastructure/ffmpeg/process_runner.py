"""Nonblocking, single-use Qt process adapter with bounded diagnostics."""
from PySide6.QtCore import QObject, QProcess, QTimer, Signal


class ProcessRunner(QObject):
    finished = Signal(bool, str)
    stdout = Signal(bytes)
    diagnostics = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.process.started.connect(self._started)
        self.kill_timer = QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.timeout.connect(self.process.kill)
        self._tail = ''
        self._done = False
        self._used = False
        self.cancelled = False

    def start(self, arguments: list[str]) -> None:
        if self._used:
            raise RuntimeError('ProcessRunner is single-use')
        self._used = True
        if not arguments or not arguments[0]:
            self._emit(False, 'No executable was supplied')
            return
        self.process.start(arguments[0], arguments[1:])

    def cancel(self) -> None:
        if self._done or not self._used:
            return
        self.cancelled = True
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.terminate()
            self.kill_timer.start(1000)

    def _started(self) -> None:
        if self.cancelled:
            self.process.terminate()
            self.kill_timer.start(1000)

    def _read_stdout(self) -> None:
        data = bytes(self.process.readAllStandardOutput())
        self.stdout.emit(data)
        self._append(data)

    def _read_stderr(self) -> None:
        self._append(bytes(self.process.readAllStandardError()))

    def _append(self, data: bytes) -> None:
        text = data.decode('utf-8', errors='replace')
        self._tail = (self._tail + text)[-16000:]
        if text:
            self.diagnostics.emit(text)

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._read_stdout()
        self._read_stderr()
        self._emit(not self.cancelled and code == 0 and status == QProcess.ExitStatus.NormalExit
                   and 'Error opening output' not in self._tail and 'Not overwriting' not in self._tail,
                   f'FFmpeg exit code: {code}; status: {status.name}\n{self._tail}')

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._emit(False, self.process.errorString())

    def _emit(self, success: bool, message: str) -> None:
        if not self._done:
            self._done = True
            self.kill_timer.stop()
            self.finished.emit(success, message)
