"""Independent Qt Widgets pages; all actions are wired by the application shell."""
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FilesView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Files / Inspect'))
        layout.addWidget(QLabel('Open a media file to inspect its streams and container.'))
        self.open_button = QPushButton('Open media file and inspect')
        layout.addWidget(self.open_button)
        layout.addStretch()


class RemuxView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Remux'))
        self.source_label = QLabel('Inspect a file first. Streams are copied without re-encoding.')
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)
        self.container = QComboBox()
        self.container.addItems(['Matroska (.mkv)', 'MP4 (.mp4)'])
        self.run_button = QPushButton('Remux inspected file…')
        layout.addWidget(self.container)
        layout.addWidget(self.run_button)
        layout.addStretch()


class SettingsView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('FFmpeg installation'))
        controls = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(['external', 'bundled'])
        self.folder = QLineEdit()
        self.folder.setPlaceholderText('Optional bin directory (external: empty = PATH)')
        self.browse_button = QPushButton('Browse bin folder')
        self.detect_button = QPushButton('Detect FFmpeg')
        for widget in (self.mode, self.folder, self.browse_button, self.detect_button):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.status = QLabel('FFmpeg not detected')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch()


class PlaceholderView(QWidget):
    def __init__(self, title: str, description: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        label = QLabel(description)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()
