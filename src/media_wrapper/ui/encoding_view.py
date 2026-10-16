"""Convert form: typed choices only, never FFmpeg arguments."""
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.application.conversion_service import ConversionRequest
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.remux import Container


class EncodingView(QScrollArea):
    def __init__(self, title: str = 'Convert') -> None:
        super().__init__()
        self.title = title
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        self.source = QLabel('Inspect a source first.')
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        self.form = QWidget()
        form = QFormLayout(self.form)
        self.container = QComboBox()
        self.container.addItems(['Matroska', 'MP4'])
        self.destination = QLineEdit()
        self.browse = QPushButton('Choose output…')
        form.addRow('Container', self.container)
        form.addRow('New destination', self.destination)
        form.addRow(self.browse)
        self.tracks = QTableWidget(0, 2)
        self.tracks.setHorizontalHeaderLabels(['Source track', 'Action / CPU encoder'])
        self.tracks.horizontalHeader().setStretchLastSection(True)
        self.tracks.setMinimumHeight(120)
        form.addRow(self.tracks)
        self.video_width, self.video_height = QSpinBox(), QSpinBox()
        for widget in (self.video_width, self.video_height):
            widget.setRange(0, 16384)
            widget.setSpecialValueText('Keep original')
            widget.setSingleStep(2)
        self.fps = QLineEdit()
        self.fps.setPlaceholderText('Keep original, or e.g. 30000/1001')
        self.audio_bitrate = QSpinBox()
        self.audio_bitrate.setRange(8, 512)
        self.audio_bitrate.setValue(128)
        form.addRow('Video width', self.video_width)
        form.addRow('Video height', self.video_height)
        form.addRow('Video FPS', self.fps)
        form.addRow('AAC bitrate (kb/s)', self.audio_bitrate)
        layout.addWidget(self.form)
        self.note = QLabel('Encoders are checked against your FFmpeg build before running. Copy preserves the original stream; Omit removes it explicitly. Scaling uses the exact dimensions entered.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QHBoxLayout()
        self.preview_button = QPushButton('Validate and preview')
        self.run_button = QPushButton('Run')
        self.enqueue_button = QPushButton('Add to queue')
        for button in (self.preview_button, self.run_button, self.enqueue_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(100)
        layout.addWidget(self.preview)
        self._media: MediaFile | None = None
        self._encoders: list[QComboBox] = []
        for widget in (self.destination, self.fps):
            widget.textChanged.connect(self.preview.clear)
        for widget in (self.video_width, self.video_height, self.audio_bitrate):
            widget.valueChanged.connect(self.preview.clear)
        self.container.currentIndexChanged.connect(self.preview.clear)

    def set_media(self, media: MediaFile | None, busy: bool) -> None:
        self.form.setEnabled(not busy and media is not None)
        for button in (self.preview_button, self.run_button, self.enqueue_button):
            button.setEnabled(not busy and media is not None)
        if media is self._media:
            return
        self._media = media
        self.preview.clear()
        self.source.setText(f'{self.title}: {media.path}' if media else 'Inspect a source first.')
        self.tracks.setRowCount(len(media.streams) if media else 0)
        self._encoders.clear()
        if media is None:
            self.destination.clear()
            return
        suffix = '.mkv' if self.container.currentIndex() == 0 else '.mp4'
        self.destination.setText(str(media.path.with_name(media.path.stem + '_' + self.title.lower() + suffix)))
        for row, stream in enumerate(media.streams):
            self.tracks.setItem(row, 0, QTableWidgetItem(f'{stream.index}: {stream.kind} / {stream.codec}'))
            combo = QComboBox()
            options = {'video': ['libx264', 'libx265', 'ffv1'], 'audio': ['aac', 'pcm_s16le'],
                       'subtitle': ['mov_text', 'srt', 'ass']}.get(stream.kind, [])
            combo.addItems(['copy', 'omit', *options])
            combo.setCurrentText({'video': 'libx264', 'audio': 'aac'}.get(stream.kind, 'copy'))
            combo.currentIndexChanged.connect(self.preview.clear)
            self.tracks.setCellWidget(row, 1, combo)
            self._encoders.append(combo)

    def request(self) -> ConversionRequest:
        if self._media is None or not self.destination.text().strip():
            raise ValueError('Inspect a file and choose a new destination')
        tracks = []
        for stream, combo in zip(self._media.streams, self._encoders, strict=True):
            if stream.index is None:
                if combo.currentText() != 'omit':
                    raise ValueError('Omit tracks with missing indices')
            else:
                tracks.append((stream.index, combo.currentText()))
        return ConversionRequest(Path(self.destination.text()),
                                 Container.MATROSKA if self.container.currentIndex() == 0 else Container.MP4,
                                 tuple(tracks), self.video_width.value() or None, self.video_height.value() or None,
                                 self.fps.text(), self.audio_bitrate.value() * 1000)
