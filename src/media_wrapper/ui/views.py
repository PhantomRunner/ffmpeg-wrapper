"""Independent Qt Widgets pages; all actions are wired by the application shell."""
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.media import MediaFile
from media_wrapper.ui.inspection_presenter import stream_values
from media_wrapper.ui.models.media_files import MediaFileModel
from media_wrapper.ui.models.tasks import ProgressDelegate, TaskModel
from media_wrapper.ui.widgets.combo_box import ReadableComboBox
from media_wrapper.ui.widgets.controls import (
    ActionButton,
    EmptyState,
    FieldRow,
    PanelHeader,
)


class FilesView(QWidget):
    files_dropped = Signal(object)
    streams_selected = Signal(object)
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(PanelHeader('Media Library', 'Import files, inspect their streams, then configure an operation.'))
        self.setAcceptDrops(True)
        self.empty_state = EmptyState('No media imported', 'Add or drop local media files. Select a file and inspect it to see metadata and available streams.')
        self.open_button = ActionButton('Add files…', primary=True)
        layout.addWidget(self.open_button)
        layout.addWidget(self.empty_state)
        self.file_list = QListView()
        self.file_list.setObjectName('mediaLibrary')
        self.media_model = MediaFileModel(self.file_list)
        self.file_list.setModel(self.media_model)
        self.file_list.setUniformItemSizes(True)
        self.file_list.setAccessibleName('Imported media files')
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setAcceptDrops(False)
        self.inspect_button = ActionButton('Inspect current')
        self.inspect_button.setAccessibleName('Inspect current file')
        self.inspect_selected_button = ActionButton('Inspect selected')
        self.inspect_selected_button.setAccessibleName('Inspect selected files')
        self.cancel_button = ActionButton('Cancel')
        self.cancel_button.setAccessibleName('Cancel inspection')
        self.cancel_button.setToolTip('Cancel inspection')
        self.batch_status = QLabel('')
        self.batch_status.setProperty('role', 'fieldHelp')
        self.batch_status.setWordWrap(True)
        self.clear_button = ActionButton('Clear')
        self.clear_button.setAccessibleName('Clear files')
        self.clear_button.setToolTip('Clear the media library')
        layout.addWidget(self.inspect_button)
        layout.addWidget(self.inspect_selected_button)
        controls = QHBoxLayout()
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.clear_button)
        layout.addLayout(controls)
        layout.addWidget(self.batch_status)
        layout.addWidget(self.file_list, 1)
        self.summary = QLabel('No inspected file selected.')
        self.summary.setProperty('role', 'sourceSummary')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.stream_table = QTableWidget(0, 11)
        self.stream_table.setObjectName('streamTable')
        self.stream_table.setShowGrid(False)
        self.stream_table.setAlternatingRowColors(True)
        self.stream_table.verticalHeader().hide()
        self.stream_table.verticalHeader().setDefaultSectionSize(34)
        self.stream_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stream_table.setAccessibleName('Inspected streams and remux selection')
        self.stream_table.setHorizontalHeaderLabels(['Select', 'Index', 'Type', 'Codec / subtitle type', 'Language',
                                                    'Bitrate (bit/s)', 'Frame size', 'Frame rate (fps)',
                                                    'Sample rate (Hz)', 'Channels', 'Layout'])
        self.stream_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stream_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.stream_table.itemChanged.connect(self._stream_changed)
        layout.addWidget(self.stream_table)
        self.stream_note = QLabel('Checked streams are used by Remux. Unsupported selected tracks cause a validation error.')
        self.stream_note.setProperty('role', 'fieldHelp')
        self.stream_note.setWordWrap(True)
        layout.addWidget(self.stream_note)
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
        body.setProperty('role', 'formBody')
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(PanelHeader('Remux', 'Change the container while copying compatible selected streams.'))
        self.source_label = QLabel('Inspect a file first. Streams are copied without re-encoding.')
        self.source_label.setProperty('role', 'sourceSummary')
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)
        self.tracks = QListWidget()
        self.tracks.setObjectName('remuxTracks')
        self.tracks.setMaximumHeight(120)
        self.tracks.itemChanged.connect(self._tracks_changed)
        layout.addWidget(self.tracks)
        simple = QGroupBox('Output')
        form = QVBoxLayout(simple)
        form.setSpacing(8)
        self.container = ReadableComboBox()
        for container, spec in CONTAINERS.items():
            self.container.addItem(f'{spec.label} ({spec.extension})', container.value)
        self.container.setToolTip('Copy supported streams into this container. No re-encoding is performed.')
        self.destination = QLineEdit()
        self.destination.setPlaceholderText('Choose a new destination filename')
        self.destination.setToolTip('Existing files and source replacement are refused. Use the extension shown for the chosen container.')
        self.browse_button = ActionButton('Choose output…')
        self.validation = QLabel('Inspect a file first.')
        self.validation.setProperty('role', 'fieldHelp')
        self.validation.setWordWrap(True)
        self.metadata_policy, self.chapter_policy = ReadableComboBox(), ReadableComboBox()
        for combo in (self.metadata_policy, self.chapter_policy):
            combo.addItems(['preserve', 'strip'])
        form.addWidget(FieldRow('&Metadata', self.metadata_policy))
        form.addWidget(FieldRow('&Chapters', self.chapter_policy))
        self.run_button = ActionButton('Run remux', primary=True)
        self.cancel_button = ActionButton('Cancel remux')
        self.enqueue_button = ActionButton('Add to queue')
        self.progress_label = QLabel('')
        self.progress_label.setProperty('role', 'fieldHelp')
        self.progress_label.setWordWrap(True)
        self.run_button.setToolTip('Validate the source again and copy selected supported streams. Unsupported tracks cause an error.')
        for widget in (self.container, self.destination, self.browse_button, self.validation, self.run_button, self.enqueue_button, self.cancel_button, self.progress_label):
            form.addWidget(widget)
        layout.addWidget(simple)
        self.advanced_toggle = QCheckBox('Advanced details')
        self.advanced_toggle.setProperty('role', 'disclosure')
        layout.addWidget(self.advanced_toggle)
        self.advanced = QGroupBox('Generated argument array')
        self.advanced.setProperty('role', 'advancedSection')
        advanced_layout = QVBoxLayout(self.advanced)
        self.preview_button = ActionButton('Validate and preview')
        self.preview_button.setToolTip('Probe the source and validate all streams in the background without creating output.')
        self.preview = QTextEdit()
        self.preview.setProperty('role', 'code')
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText('Preview validates the selection. Run generates a fresh temporary path and displays the actual executed arguments.')
        advanced_layout.addWidget(self.preview_button)
        advanced_layout.addWidget(self.preview)
        layout.addWidget(self.advanced)
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.advanced.hide()

        from media_wrapper.ui.parameter_help import install_help
        install_help(self, ('container', 'destination', 'tracks', 'metadata_policy', 'chapter_policy'))

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
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)
        layout.addWidget(PanelHeader('Settings', 'Binary installation, runtime capabilities and diagnostics.'))

        def section(title: str) -> QVBoxLayout:
            card = QFrame()
            card.setProperty('role', 'settingsSection')
            content = QVBoxLayout(card)
            content.setContentsMargins(12, 12, 12, 12)
            content.setSpacing(8)
            heading = QLabel(title)
            heading.setProperty('role', 'sectionTitle')
            content.addWidget(heading)
            layout.addWidget(card)
            return content

        installation = section('FFmpeg installation')
        self.mode = ReadableComboBox()
        self.mode.addItems(['external', 'bundled'])
        self.mode.setToolTip('External uses PATH or your chosen folder. Bundled requires an explicit folder; there is no fallback.')
        self.folder = QLineEdit()
        self.folder.setPlaceholderText('Optional bin directory (external: empty = PATH)')
        self.browse_button = ActionButton('Browse bin folder')
        self.detect_button = ActionButton('Detect FFmpeg')
        installation.addWidget(FieldRow('Binary source', self.mode))
        installation.addWidget(self.folder)
        controls = QHBoxLayout()
        controls.addWidget(self.browse_button)
        controls.addWidget(self.detect_button)
        controls.addStretch()
        installation.addLayout(controls)
        self.sidecar_button = ActionButton('Select bundled sidecar folder')
        self.sidecar_button.setToolTip('Explicitly select ffmpeg/bin beside the packaged executable. Missing files are reported; PATH is not used as a fallback.')
        installation.addWidget(self.sidecar_button)
        self.status = QLabel('FFmpeg not detected')
        self.status.setProperty('role', 'sourceSummary')
        self.status.setWordWrap(True)
        installation.addWidget(self.status)
        hardware = section('Hardware & capabilities')
        self.test_gpu = QCheckBox('Also runtime-test listed GPU encoders (short synthetic encodes)')
        self.gpu_device = QLineEdit()
        self.gpu_device.setPlaceholderText('Optional VAAPI render device, e.g. /dev/dri/renderD128')
        self.scan_button = ActionButton('Scan build / refresh capabilities')
        self.cancel_scan = ActionButton('Cancel capability scan')
        self.capabilities = QTextEdit()
        self.capabilities.setProperty('role', 'code')
        self.capabilities.setReadOnly(True)
        self.capabilities.setMinimumHeight(110)
        self.capabilities.setMaximumHeight(200)
        self.capabilities.setPlaceholderText('Detected encoders, formats and GPU capabilities appear here.')
        hardware.addWidget(self.test_gpu)
        hardware.addWidget(self.gpu_device)
        scan_actions = QHBoxLayout()
        scan_actions.addWidget(self.scan_button)
        scan_actions.addWidget(self.cancel_scan)
        scan_actions.addStretch()
        hardware.addLayout(scan_actions)
        hardware.addWidget(self.capabilities)
        diagnostics = section('Diagnostics')
        self.log_level = ReadableComboBox()
        self.log_level.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR'])
        self.private_diagnostics = QCheckBox('Include private paths, executed arguments and raw task logs')
        self.private_diagnostics.setToolTip('Leave unchecked for a shareable summary without paths, metadata or raw errors.')
        self.export_diagnostics = ActionButton('Export diagnostics…')
        diagnostics.addWidget(FieldRow('Diagnostic log &level', self.log_level))
        for widget in (self.private_diagnostics, self.export_diagnostics):
            diagnostics.addWidget(widget)
        layout.addStretch()


class PlaceholderView(QWidget):
    def __init__(self, title: str, description: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.addWidget(QLabel(title))
        label = QLabel(description)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()


class QueueView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        layout.addWidget(PanelHeader('Processing queue', 'Review tasks, follow progress and manage completed outputs.'))
        self.setToolTip('Sequential processing queue. Retry creates a new attempt; partial outputs and diagnostics are retained.')
        direct_row = QHBoxLayout()
        self.direct_status = QLabel()
        self.direct_status.setProperty('role', 'fieldHelp')
        self.direct_status.setWordWrap(True)
        self.cancel_direct = ActionButton('Cancel direct Remux')
        direct_row.addWidget(self.direct_status, 1)
        direct_row.addWidget(self.cancel_direct)
        layout.addLayout(direct_row)
        buttons = QHBoxLayout()
        self.start_button = ActionButton('Start queue', primary=True)
        self.cancel_button = ActionButton('Cancel selected')
        self.cancel_all_button = ActionButton('Cancel all')
        self.retry_button = ActionButton('Retry')
        self.cpu_retry_button = ActionButton('Retry on CPU')
        self.open_output = ActionButton('Open output folder')
        self.save_definitions = ActionButton('Save queue…')
        self.load_definitions = ActionButton('Load queue…')
        self.save_definitions.setToolTip('Save unfinished intent with local paths; loading revalidates and never starts tasks.')
        for button in (self.start_button, self.cancel_button, self.cancel_all_button,
                       self.retry_button, self.cpu_retry_button):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        documents = QHBoxLayout()
        documents.addWidget(self.open_output)
        documents.addStretch()
        documents.addWidget(self.load_definitions)
        documents.addWidget(self.save_definitions)
        layout.addLayout(documents)
        history = QHBoxLayout()
        self.history_summary = QLabel('No finished history')
        self.history_summary.setProperty('role', 'fieldHelp')
        self.history_summary.setAccessibleName('Queue history count')
        history.addWidget(self.history_summary, 1)
        self.clear_history = ActionButton('Clear History')
        self.clear_history.setToolTip('Remove finished session entries and their in-memory diagnostics. Media files are never deleted.')
        history.addWidget(self.clear_history)
        layout.addLayout(history)
        self.empty_state = EmptyState('No tasks queued', 'Configure an operation in the Inspector, then Add to queue.')
        layout.addWidget(self.empty_state)
        self.table = QTableView()
        self.table.setObjectName('queueTable')
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.task_model = TaskModel(self.table)
        self.table.setModel(self.task_model)
        self.table.setItemDelegateForColumn(3, ProgressDelegate(self.table))
        self.table.setAccessibleName('Processing tracks with accessible text percentages')
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.horizontalHeader().setFixedHeight(34)
        self.table.setWordWrap(False)
        self.table.setMinimumHeight(70)
        layout.addWidget(self.table, 1)
        self.details_toggle = QCheckBox('Task details and diagnostics')
        self.details_toggle.setProperty('role', 'disclosure')
        layout.addWidget(self.details_toggle)
        self.details = QTextEdit()
        self.details.setProperty('role', 'code')
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(130)
        self.details_toggle.toggled.connect(self.details.setVisible)
        self.details.hide()
        layout.addWidget(self.details)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)

    def context_menu(self, point) -> None:
        from PySide6.QtWidgets import QMenu
        index = self.table.indexAt(point)
        if index.isValid():
            self.table.selectRow(index.row())
        menu = QMenu(self.table)
        for button in (self.cancel_button, self.retry_button, self.cpu_retry_button, self.open_output):
            action = menu.addAction(button.text())
            action.setEnabled(button.isEnabled())
            action.triggered.connect(button.click)
        menu.exec(self.table.viewport().mapToGlobal(point))
