"""Qt application adapter for executing a prepared remux command."""
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from media_wrapper.infrastructure.ffmpeg.process_runner import ProcessRunner


class RemuxTask(QObject):
    finished = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.runner = ProcessRunner(self)
        self.runner.finished.connect(self.finished)

    def start(self, command: list[str]):
        destination = Path(command[-1])
        if destination.exists() or destination.is_symlink():
            self.finished.emit(False, 'Destination already exists; choose a new filename')
            return
        self.runner.start(command)
