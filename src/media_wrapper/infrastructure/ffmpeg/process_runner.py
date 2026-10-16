"""Qt asynchronous process adapter; retains only a bounded diagnostic tail."""
from PySide6.QtCore import QObject, QProcess, Signal


class ProcessRunner(QObject):
    finished = Signal(bool, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self._tail = ''
        self._done = False

    def start(self, arguments: list[str]) -> None:
        self.process.start(arguments[0], arguments[1:])

    def _read(self) -> None:
        self._tail = (self._tail + bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace'))[-16000:]

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._read()
        self._emit(code == 0 and status == QProcess.ExitStatus.NormalExit
                   and 'Error opening output' not in self._tail
                   and 'Not overwriting' not in self._tail,
                   f'FFmpeg exit code: {code}; status: {status.name}\n{self._tail}')

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._emit(False, self.process.errorString())

    def _emit(self, success: bool, message: str) -> None:
        if not self._done:
            self._done = True
            self.finished.emit(success, message)
