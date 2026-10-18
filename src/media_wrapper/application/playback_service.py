"""Playback lifecycle separate from inspection, conversion and queue state."""
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QMediaPlayer

from media_wrapper.infrastructure.playback import QtPlaybackBackend


class PlaybackService(QObject):
    changed = Signal()
    position_changed = Signal('qlonglong')

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.backend = QtPlaybackBackend(self)
        self.source: Path | None = None
        self.error = ''
        player = self.backend.player
        for signal in (player.durationChanged, player.seekableChanged, player.playbackStateChanged,
                       player.mediaStatusChanged):
            signal.connect(self.changed)
        player.positionChanged.connect(self.position_changed)
        player.positionChanged.connect(self.changed)
        player.errorOccurred.connect(self._error)

    @property
    def duration(self) -> int:
        return self.backend.player.duration()

    @property
    def position(self) -> int:
        return self.backend.player.position()

    @property
    def playing(self) -> bool:
        return self.backend.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @property
    def ready(self) -> bool:
        return bool(self.source and not self.error and self.backend.player.mediaStatus() in (
            QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia,
            QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.EndOfMedia))

    @property
    def seekable(self) -> bool:
        return self.ready and self.backend.player.isSeekable() and self.duration > 0

    def set_source(self, source: Path | None) -> None:
        if source == self.source:
            return
        self.source, self.error = source, ''
        self.backend.load(source)
        self.position_changed.emit(0)
        self.changed.emit()

    def toggle(self) -> None:
        if self.ready:
            if self.playing:
                self.backend.player.pause()
            else:
                self.backend.player.play()

    def seek(self, position: int) -> None:
        if self.seekable:
            self.backend.player.setPosition(max(0, min(position, self.duration)))

    def bind_video(self, surface) -> None:
        self.backend.player.setVideoOutput(surface)

    def _error(self, code, message: str) -> None:
        if code != QMediaPlayer.Error.NoError:
            self.error = message or 'The media backend could not decode this source.'
            self.changed.emit()

    def close(self) -> None:
        self.source = None
        self.backend.close()
