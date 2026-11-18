"""Nonblocking, single-use Qt process adapter with streamed diagnostics."""
from codecs import getincrementaldecoder

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from media_wrapper.infrastructure.ffmpeg.progress_parser import ProgressParser
from media_wrapper.infrastructure.process_environment import external_environment
from media_wrapper.infrastructure.process_lifetime import owned_command


class ProcessRunner(QObject):
    finished = Signal(bool, str)
    stdout = Signal(bytes)
    diagnostics = Signal(str)
    progress = Signal(object)

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
        self.error_output = ''
        self._stdout_decoder = getincrementaldecoder('utf-8')('replace')
        self._stderr_decoder = getincrementaldecoder('utf-8')('replace')
        self._done = False
        self._used = False
        self.cancelled = False
        self.parser = ProgressParser()

    def start(self, arguments: list[str], duration: float | None = None) -> None:
        if self._used:
            raise RuntimeError('ProcessRunner is single-use')
        self._used = True
        self.parser = ProgressParser(duration)
        if not arguments or not arguments[0]:
            self._emit(False, 'No executable was supplied')
            return
        environment = QProcessEnvironment()
        for key, value in external_environment().items():
            environment.insert(key, value)
        self.process.setProcessEnvironment(environment)
        try:
            command = owned_command(arguments)
        except OSError as error:
            self.error_output = str(error)
            self._emit(False, self.error_output)
            return
        self.process.start(command[0], command[1:])

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
        for progress in self.parser.feed(data):
            self.progress.emit(progress)
        self._append(self._stdout_decoder.decode(data))

    def _read_stderr(self) -> None:
        data = bytes(self.process.readAllStandardError())
        self._append_error(self._stderr_decoder.decode(data))

    def _append_error(self, text: str) -> None:
        self.error_output = (self.error_output + text)[-16000:]
        self._append(text)

    def _append(self, text: str) -> None:
        self._tail = (self._tail + text)[-16000:]
        if text:
            self.diagnostics.emit(text)

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._read_stdout()
        self._read_stderr()
        self._append(self._stdout_decoder.decode(b'', final=True))
        self._append_error(self._stderr_decoder.decode(b'', final=True))
        self._emit(not self.cancelled and code == 0 and status == QProcess.ExitStatus.NormalExit
                   and 'Error opening output' not in self._tail and 'Not overwriting' not in self._tail,
                   f'FFmpeg exit code: {code}; status: {status.name}\n{self._tail}')

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.error_output = self.process.errorString()
            self._emit(False, self.process.errorString())

    def _emit(self, success: bool, message: str) -> None:
        if not self._done:
            self._done = True
            self.kill_timer.stop()
            self.finished.emit(success, message)
