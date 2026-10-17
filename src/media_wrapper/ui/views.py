"""Independent Qt Widgets pages; all actions are wired by the application shell."""
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.media import MediaFile
from media_wrapper.ui.inspection_presenter import stream_values


class FilesView(QWidget):
    files_dropped = Signal(object)
    streams_selected = Signal(object)
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Files / Inspect'))
        self.setAcceptDrops(True)
        layout.addWidget(QLabel('Add or drop local media files. Select files to inspect; choose a row to review its results.'))
        self.open_button = QPushButton('Add files…')
        layout.addWidget(self.open_button)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setAcceptDrops(False)
        layout.addWidget(self.file_list)
        self.inspect_button = QPushButton('Inspect current file')
        self.inspect_selected_button = QPushButton('Inspect selected files')
        self.cancel_button = QPushButton('Cancel inspection')
        self.batch_status = QLabel('')
        self.batch_status.setWordWrap(True)
        self.clear_button = QPushButton('Clear files')
        layout.addWidget(self.inspect_button)
        layout.addWidget(self.inspect_selected_button)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.batch_status)
        layout.addWidget(self.clear_button)
        self.summary = QLabel('No inspected file selected.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.stream_table = QTableWidget(0, 11)
        self.stream_table.setHorizontalHeaderLabels(['Select', 'Index', 'Type', 'Codec / subtitle type', 'Language',
                                                    'Bitrate (bit/s)', 'Frame size', 'Frame rate (fps)',
                                                    'Sample rate (Hz)', 'Channels', 'Layout'])
        self.stream_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stream_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.stream_table.itemChanged.connect(self._stream_changed)
        layout.addWidget(self.stream_table)
        note = QLabel('Checked streams are used by Remux. Unsupported selected tracks cause a validation error.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self._media: MediaFile | None = None

    def set_media(self, media: MediaFile | None, selected: tuple[int, ...]) -> None:
        with QSignalBlocker(self.stream_table):
            if media is not self._media:
                self._media = media
                self.stream_table.setRowCount(len(media.streams) if media else 0)
                self.summary.setText(f'Container: {media.format_name} | Duration: {media.duration if media.duration is not None else "unknown"} s | '
                                     f'Size: {media.size_bytes if media.size_bytes is not None else "unknown"} bytes | '
                                     f'Bitrate: {media.bit_rate if media.bit_rate is not None else "unknown"} bit/s'
                                     if media else 'No inspected file selected.')
                if media:
                    for row, stream in enumerate(media.streams):
                        checkbox = QTableWidgetItem()
                        checkbox.setData(Qt.ItemDataRole.UserRole, stream.index)
                        checkbox.setFlags(Qt.ItemFlag.ItemIsEnabled | (Qt.ItemFlag.ItemIsUserCheckable if stream.index is not None else Qt.ItemFlag.NoItemFlags))
                        self.stream_table.setItem(row, 0, checkbox)
                        for column, value in enumerate(stream_values(stream), 1):
                            item = QTableWidgetItem(value)
                            item.setToolTip(stream.title or stream.codec_long_name or value)
                            self.stream_table.setItem(row, column, item)
            for row in range(self.stream_table.rowCount()):
                item = self.stream_table.item(row, 0)
                item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in selected else Qt.CheckState.Unchecked)

    def _stream_changed(self, _item: QTableWidgetItem) -> None:
        selected = tuple(self.stream_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                         for row in range(self.stream_table.rowCount())
                         if self.stream_table.item(row, 0).checkState() == Qt.CheckState.Checked
                         and self.stream_table.item(row, 0).data(Qt.ItemDataRole.UserRole) is not None)
        self.streams_selected.emit(selected)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if self.isEnabled() and urls and all(url.isLocalFile() for url in urls):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if self.isEnabled() and urls and all(url.isLocalFile() for url in urls):
            self.files_dropped.emit([Path(url.toLocalFile()) for url in urls])
            event.acceptProposedAction()


class RemuxView(QScrollArea):
    streams_selected = Signal(object)
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.addWidget(QLabel('Remux'))
        self.source_label = QLabel('Inspect a file first. Streams are copied without re-encoding.')
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)
        self.tracks = QListWidget()
        self.tracks.setMaximumHeight(120)
        self.tracks.itemChanged.connect(self._tracks_changed)
        layout.addWidget(self.tracks)
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
        self.metadata_policy, self.chapter_policy = QComboBox(), QComboBox()
        for combo in (self.metadata_policy, self.chapter_policy):
            combo.addItems(['preserve', 'strip'])
        form.addWidget(QLabel('Metadata (global and selected tracks)'))
        form.addWidget(self.metadata_policy)
        form.addWidget(QLabel('Chapters'))
        form.addWidget(self.chapter_policy)
        self.run_button = QPushButton('Run remux')
        self.cancel_button = QPushButton('Cancel remux')
        self.enqueue_button = QPushButton('Add to queue')
        self.progress_label = QLabel('')
        self.progress_label.setWordWrap(True)
        self.run_button.setToolTip('Validate the source again and copy selected supported streams. Unsupported tracks cause an error.')
        for widget in (self.container, self.destination, self.browse_button, self.validation, self.run_button, self.enqueue_button, self.cancel_button, self.progress_label):
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
        self.preview.setPlaceholderText('Preview validates the selection. Run generates a fresh temporary path and displays the actual executed arguments.')
        advanced_layout.addWidget(self.preview_button)
        advanced_layout.addWidget(self.preview)
        layout.addWidget(self.advanced)
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.advanced.hide()

    def set_tracks(self, media: MediaFile | None, selected: tuple[int, ...]) -> None:
        with QSignalBlocker(self.tracks):
            self.tracks.clear()
            for stream in media.streams if media else ():
                item = QListWidgetItem(f'{stream.index}: {stream.kind} / {stream.codec} / {stream.language or "unknown language"}')
                item.setData(Qt.ItemDataRole.UserRole, stream.index)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | (Qt.ItemFlag.ItemIsUserCheckable if stream.index is not None else Qt.ItemFlag.NoItemFlags))
                item.setCheckState(Qt.CheckState.Checked if stream.index in selected else Qt.CheckState.Unchecked)
                self.tracks.addItem(item)

    def _tracks_changed(self, _item: QListWidgetItem) -> None:
        self.streams_selected.emit(tuple(self.tracks.item(i).data(Qt.ItemDataRole.UserRole)
                                         for i in range(self.tracks.count())
                                         if self.tracks.item(i).checkState() == Qt.CheckState.Checked))


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
        self.sidecar_button = QPushButton('Select bundled sidecar folder')
        self.sidecar_button.setToolTip('Explicitly select ffmpeg/bin beside the packaged executable. Missing files are reported; PATH is not used as a fallback.')
        layout.addWidget(self.sidecar_button)
        self.status = QLabel('FFmpeg not detected')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.test_gpu = QCheckBox('Also runtime-test listed GPU encoders (short synthetic encodes)')
        self.gpu_device = QLineEdit()
        self.gpu_device.setPlaceholderText('Optional VAAPI render device, e.g. /dev/dri/renderD128')
        self.scan_button = QPushButton('Scan build / refresh capabilities')
        self.cancel_scan = QPushButton('Cancel capability scan')
        self.capabilities = QTextEdit()
        self.capabilities.setReadOnly(True)
        for widget in (self.test_gpu, self.gpu_device, self.scan_button, self.cancel_scan, self.capabilities):
            layout.addWidget(widget)
        self.log_level = QComboBox()
        self.log_level.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR'])
        self.private_diagnostics = QCheckBox('Include private paths, executed arguments and raw task logs')
        self.private_diagnostics.setToolTip('Leave unchecked for a shareable summary without paths, metadata or raw errors.')
        self.export_diagnostics = QPushButton('Export diagnostics…')
        layout.addWidget(QLabel('Local diagnostic log level'))
        for widget in (self.log_level, self.private_diagnostics, self.export_diagnostics):
            layout.addWidget(widget)
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


class QueueView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        note = QLabel('Sequential queue for this session. Failures and cancellations leave later jobs running. Partial files are retained; retry creates a new attempt.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.save_definitions = QPushButton('Save unfinished definitions…')
        self.load_definitions = QPushButton('Load definitions…')
        self.save_definitions.setToolTip('Stores source/output paths and settings. Loading revalidates sources and creates new pending attempts; no mid-encode checkpoints.')
        definitions = QHBoxLayout()
        definitions.addWidget(self.save_definitions)
        definitions.addWidget(self.load_definitions)
        layout.addLayout(definitions)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Source', 'Output', 'Status', 'Progress'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        self.start_button = QPushButton('Start queue')
        self.cancel_button = QPushButton('Cancel selected')
        self.cancel_all_button = QPushButton('Cancel all')
        self.retry_button = QPushButton('Retry selected')
        self.cpu_retry_button = QPushButton('Retry on CPU')
        self.cpu_retry_button.setToolTip('Explicitly create a new CPU attempt. Previous diagnostics and partial output are retained.')
        for button in (self.start_button, self.cancel_button, self.cancel_all_button, self.retry_button, self.cpu_retry_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details)
