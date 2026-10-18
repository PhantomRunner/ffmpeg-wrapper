"""Preview transport bound to the application playback service."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from media_wrapper.ui.widgets.controls import ActionButton


def timecode(milliseconds: int) -> str:
    seconds = max(0, milliseconds) // 1000
    return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'


class PlaybackPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.service = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel('Select a source for playback.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        try:
            from PySide6.QtMultimediaWidgets import QVideoWidget

            from media_wrapper.application.playback_service import PlaybackService
            self.service = PlaybackService(self)
            self.video = QVideoWidget()
            self.video.setMinimumSize(160, 90)
            self.service.bind_video(self.video)
            layout.addWidget(self.video, 1)
        except (ImportError, OSError, RuntimeError) as error:
            self.status.setText(f'Playback unavailable: {error}')
        layout.addWidget(self.status)
        transport = QHBoxLayout()
        self.play = ActionButton('Play')
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 10000)
        self.seek.setAccessibleName('Playback position')
        self.time = QLabel('00:00:00 / 00:00:00')
        for widget in (self.play, self.seek, self.time):
            transport.addWidget(widget)
        layout.addLayout(transport)
        self.play.setEnabled(False)
        self.seek.setEnabled(False)
        if self.service:
            self.service.changed.connect(self.render)
            self.play.clicked.connect(self.service.toggle)
            self.seek.sliderReleased.connect(self.commit_seek)
            self.seek.actionTriggered.connect(self.keyboard_seek)

    def commit_seek(self) -> None:
        self.service.seek(round(self.seek.value() * self.service.duration / 10000))

    def keyboard_seek(self, action: int) -> None:
        if not self.seek.isSliderDown():
            self.service.seek(round(self.seek.sliderPosition() * self.service.duration / 10000))

    def set_source(self, source) -> None:
        if self.service:
            self.service.set_source(source)

    def render(self) -> None:
        service = self.service
        self.play.setText('Pause' if service.playing else 'Play')
        self.play.setAccessibleName(self.play.text())
        self.play.setEnabled(service.ready)
        self.seek.setEnabled(service.seekable)
        self.time.setText(f'{timecode(service.position)} / {timecode(service.duration)}')
        if not self.seek.isSliderDown():
            self.seek.setValue(round(service.position * 10000 / service.duration) if service.duration else 0)
        self.status.setText(('Playback error: ' + service.error + '\nTry another source or a supported preview codec.')
                            if service.error else 'Select a source for playback.' if not service.source
                            else 'Ready — audio/video playback' if service.ready else 'Loading preview…')

    def shutdown(self) -> None:
        if self.service:
            self.service.close()
