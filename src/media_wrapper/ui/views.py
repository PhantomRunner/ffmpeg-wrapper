"""Independent Qt Widgets pages; all actions are wired by the application shell."""
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class FilesView(QWidget):
    files_dropped = Signal(object)
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Files / Inspect'))
        self.setAcceptDrops(True)
        layout.addWidget(QLabel('Add or drop local media files. Inspect the current file.'))
        self.open_button = QPushButton('Add files…')
        layout.addWidget(self.open_button)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setAcceptDrops(False)
        layout.addWidget(self.file_list)
        self.inspect_button = QPushButton('Inspect current file')
        self.clear_button = QPushButton('Clear files')
        layout.addWidget(self.inspect_button)
        layout.addWidget(self.clear_button)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if self.isEnabled() and urls and all(url.isLocalFile() for url in urls):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if self.isEnabled() and urls and all(url.isLocalFile() for url in urls):
            self.files_dropped.emit([Path(url.toLocalFile()) for url in urls])
            event.acceptProposedAction()


class RemuxView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Remux'))
        self.source_label = QLabel('Inspect a file first. Streams are copied without re-encoding.')
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)
        simple = QGroupBox('Output')
        form = QVBoxLayout(simple)
        self.container = QComboBox()
        self.container.addItems(['Matroska (.mkv)', 'MP4 (.mp4)'])
        self.container.setToolTip('Copy supported streams into this container. No re-encoding is performed.')
        self.destination = QLineEdit()
        self.destination.setPlaceholderText('Choose a new destination filename')
        self.destination.setToolTip('Existing files and source replacement are refused. Use .mkv or .mp4 for the chosen container.')
        self.browse_button = QPushButton('Choose output…')
        self.validation = QLabel('Inspect a file first.')
        self.validation.setWordWrap(True)
        self.run_button = QPushButton('Run remux')
        self.run_button.setToolTip('Validate the source again and copy all supported streams. Unsupported tracks cause an error.')
        for widget in (self.container, self.destination, self.browse_button, self.validation, self.run_button):
            form.addWidget(widget)
        layout.addWidget(simple)
        self.advanced_toggle = QCheckBox('Advanced details')
        layout.addWidget(self.advanced_toggle)
        self.advanced = QGroupBox('Generated argument array')
        advanced_layout = QVBoxLayout(self.advanced)
        self.preview_button = QPushButton('Validate and preview')
        self.preview_button.setToolTip('Probe the source and validate all streams in the background without creating output.')
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText('Validate to display the exact argument array. Changing inputs clears the preview.')
        advanced_layout.addWidget(self.preview_button)
        advanced_layout.addWidget(self.preview)
        layout.addWidget(self.advanced)
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.advanced.hide()


class SettingsView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('FFmpeg installation'))
        controls = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(['external', 'bundled'])
        self.mode.setToolTip('External uses PATH or your chosen folder. Bundled requires an explicit folder; there is no fallback.')
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
