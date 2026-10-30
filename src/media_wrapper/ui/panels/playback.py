"""Preview transport bound to the application playback service."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.ui.theme.icons import icon
from media_wrapper.ui.theme.tokens import COLORS
from media_wrapper.ui.widgets.controls import ActionButton


def timecode(milliseconds: int) -> str:
    seconds = max(0, milliseconds) // 1000
    return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'


class PlaybackPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName('playbackPanel')
        self.service = None
        self.video = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.surface = QFrame()
        self.surface.setObjectName('previewSurface')
        self.surface.setMinimumSize(160, 90)
        self.surface_layout = QStackedLayout(self.surface)
        self.surface_layout.setContentsMargins(0, 0, 0, 0)
        self.placeholder = QWidget()
        placeholder_layout = QVBoxLayout(self.placeholder)
        placeholder_layout.setContentsMargins(8, 8, 8, 8)
        placeholder_layout.setSpacing(6)
        preview_icon = QLabel()
        preview_icon.setPixmap(icon('video', size=26, color=COLORS['secondary']).pixmap(26, 26))
        preview_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_text = QLabel('Select a file to preview')
        self.placeholder_text.setProperty('role', 'secondary')
        self.placeholder_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addWidget(preview_icon)
        placeholder_layout.addWidget(self.placeholder_text)
        placeholder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.surface_layout.addWidget(self.placeholder)
        layout.addWidget(self.surface, 1)
        self.status = QLabel('Select a source for playback.')
        self.status.setProperty('role', 'playbackStatus')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        try:
            from PySide6.QtMultimediaWidgets import QVideoWidget

            from media_wrapper.application.playback_service import PlaybackService
            self.service = PlaybackService(self)
            self.video = QVideoWidget()
            self.video.setMinimumSize(160, 90)
            self.service.bind_video(self.video)
            self.surface_layout.addWidget(self.video)
        except (ImportError, OSError, RuntimeError) as error:
            self.status.setText(f'Playback unavailable: {error}')
            self.placeholder_text.setText('Preview unavailable')
        layout.addWidget(self.status)
        transport_panel = QWidget()
        transport_panel.setObjectName('playbackTransport')
        transport = QHBoxLayout(transport_panel)
        transport.setContentsMargins(0, 0, 0, 0)
        transport.setSpacing(10)
        self.play = ActionButton('Play')
        self.play.setObjectName('playButton')
        self.play.setToolTip('Play or pause source preview')
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setObjectName('playbackSeek')
        self.seek.setRange(0, 10000)
        self.seek.setAccessibleName('Playback position')
        self.seek.setCursor(Qt.CursorShape.PointingHandCursor)
        self.time = QLabel('00:00:00 / 00:00:00')
        self.time.setProperty('role', 'timecode')
        self.time.setAccessibleName('Current playback time and source duration')
        transport.addWidget(self.play)
        transport.addWidget(self.seek, 1)
        transport.addWidget(self.time)
        layout.addWidget(transport_panel)
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
        self.play.setIcon(icon('pause' if service.playing else 'play'))
        self.play.setAccessibleName(self.play.text())
        self.play.setEnabled(service.ready)
        self.seek.setEnabled(service.seekable)
        self.time.setText(f'{timecode(service.position)} / {timecode(service.duration)}')
        if not self.seek.isSliderDown():
            self.seek.setValue(round(service.position * 10000 / service.duration) if service.duration else 0)
        self.status.setText('Playback error — try another source.'
                            if service.error else 'Select a source for playback.' if not service.source
                            else 'Ready — audio/video playback' if service.ready else 'Loading preview…')
        self.status.setToolTip(service.error + '\nTry another source or a supported preview codec.' if service.error else self.status.text())
        self.surface_layout.setCurrentWidget(self.video if self.video is not None and service.source and service.ready
                                             else self.placeholder)
        self.placeholder_text.setText('Preview unavailable' if service.error else
                                      'Loading preview…' if service.source else 'Select a file to preview')

    def shutdown(self) -> None:
        if self.service:
            self.service.close()
