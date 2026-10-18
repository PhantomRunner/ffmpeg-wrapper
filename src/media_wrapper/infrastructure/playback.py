"""Qt's asynchronous media backend; independent of processing FFmpeg binaries."""
from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class QtPlaybackBackend(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.7)
        self.player.setAudioOutput(self.audio)

    def load(self, path) -> None:
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(path)) if path else QUrl())

    def close(self) -> None:
        self.load(None)
        self.player.setVideoOutput(None)
