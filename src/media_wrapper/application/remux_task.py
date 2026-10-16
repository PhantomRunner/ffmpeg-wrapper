"""Qt application adapter for executing a prepared remux command."""
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from media_wrapper.application.errors import ApplicationError, report_failure
from media_wrapper.infrastructure.ffmpeg.process_runner import ProcessRunner


class RemuxTask(QObject):
    finished = Signal(bool, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.runner = ProcessRunner(self)
        self.runner.finished.connect(self._finished)

    def start(self, command: list[str]) -> None:
        try:
            if not command:
                raise ApplicationError('Remux failed. No command was prepared; select the input file again.')
            destination = Path(command[-1])
            if destination.exists() or destination.is_symlink():
                raise ApplicationError('Remux failed. Destination already exists; choose a new filename')
            self.runner.start(command)
        except Exception as error:  # noqa: BLE001 - asynchronous application boundary
            self.finished.emit(False, report_failure('Remux', error))

    @Slot(bool, str)
    def _finished(self, success: bool, details: str) -> None:
        if success:
            self.finished.emit(True, details)
        else:
            error = ApplicationError(
                'Remux failed. Check the selected binaries and destination permissions. '
                'A partial output may remain; choose a new filename to retry. '
                'See the diagnostic log for FFmpeg details.', details)
            self.finished.emit(False, report_failure('Remux', error))
