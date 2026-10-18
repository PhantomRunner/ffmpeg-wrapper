"""Desktop shell: page navigation and bindings to presentation state."""
import json
from pathlib import Path

from PySide6.QtCore import (
    QItemSelectionModel,
    QSettings,
    QSignalBlocker,
    Qt,
    QThread,
    QUrl,
    Slot,
)
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.application.operation_task import OperationTask
from media_wrapper.application.remux_task import RemuxTask
from media_wrapper.application.settings_service import SettingsService
from media_wrapper.domain.capabilities import GPU_ENCODERS
from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.operations import PreservationPolicy
from media_wrapper.domain.preferences import Preferences
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.ui.encoding_view import EncodingView
from media_wrapper.ui.inspection_presenter import format_inspection
from media_wrapper.ui.theme import apply_theme
from media_wrapper.ui.view_model import DesktopViewModel
from media_wrapper.ui.views import (
    FilesView,
    QueueView,
    RemuxView,
    SettingsView,
)
from media_wrapper.ui.widgets.controls import EmptyState, PanelHeader, StatusChip
from media_wrapper.ui.workspace import Workspace, operation_panel, scroll_panel


class MainWindow(QMainWindow):
    def __init__(self, diagnostic_status: str = '', settings_service: SettingsService | None = None, layout_settings: QSettings | None = None) -> None:
        super().__init__()
        apply_theme(self)
        self.setWindowTitle('Media Wrapper — FFmpeg UI')
        self.settings_service = settings_service
        preferences = settings_service.load() if settings_service else Preferences()
        self.resize(preferences.width if preferences.width >= 960 else 1280,
                    max(640, preferences.height) if preferences.width >= 960 else 720)
        self.setMinimumSize(960, 640)
        if settings_service and settings_service.warning:
            diagnostic_status += ' | ' + settings_service.warning
        self.statusBar().showMessage(diagnostic_status)
        self.activity = StatusChip()
        self.statusBar().addPermanentWidget(self.activity)
        self.binary_summary = QLabel('FFmpeg unavailable')
        self.statusBar().addWidget(self.binary_summary, 1)
        self.model = DesktopViewModel(self)
        self.model.state.container = Container(preferences.container)
        self.model.state.recent_destination = Path(preferences.recent_destination) if preferences.recent_destination else None
        root = QWidget()
        root.setObjectName('workspaceRoot')
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)
        self.navigation = QListWidget()
        self.navigation.setObjectName('modeNavigation')
        self.navigation.setAccessibleName('Workspace modes')
        self.navigation.addItems(['Inspect', 'Remux', 'Convert', 'Compress', 'Queue', 'Settings'])
        self.navigation.setMaximumWidth(170)
        self.pages = QStackedWidget()
        self.files_view = FilesView()
        self.remux_view = RemuxView()
        self.settings_view = SettingsView()
        self.settings_view.log_level.setCurrentText(preferences.log_level)
        from media_wrapper.application.diagnostic_service import set_log_level
        set_log_level(preferences.log_level)
        self.settings_view.log_level.currentTextChanged.connect(set_log_level)
        self.settings_view.export_diagnostics.clicked.connect(self.export_diagnostics)
        self.queue_view = QueueView()
        self.convert_view = EncodingView()
        self.compress_view = EncodingView('Compress')
        metadata = QWidget()
        metadata_layout = QVBoxLayout(metadata)
        metadata_layout.addWidget(PanelHeader('Media Inspector', 'Metadata and Remux stream selection'))
        metadata_layout.addWidget(self.files_view.summary)
        metadata_layout.addWidget(self.files_view.stream_table)
        metadata_layout.addWidget(self.files_view.stream_note)
        for page in (metadata, operation_panel(self.remux_view, remux=True),
                     operation_panel(self.convert_view), operation_panel(self.compress_view),
                     EmptyState('Queue controls', 'Use the Processing Timeline below to start, cancel, retry and inspect jobs.'),
                     scroll_panel(self.settings_view)):
            self.pages.addWidget(page)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(preferences.page)
        self.mode = self.settings_view.mode
        self.folder = self.settings_view.folder
        self.status = self.settings_view.status
        self.detect_button = self.settings_view.detect_button
        self.choose_file_button = self.files_view.open_button
        self.container = self.remux_view.container
        self.remux_button = self.remux_view.run_button
        self.mode.setCurrentText(preferences.binary_mode)
        self.folder.setText(preferences.binary_directory)
        self.remux_view.advanced_toggle.setChecked(preferences.advanced)
        self.settings_view.browse_button.clicked.connect(self.choose_folder)
        self.settings_view.sidecar_button.clicked.connect(self.select_sidecar)
        self.detect_button.clicked.connect(self.detect)
        self.settings_view.scan_button.clicked.connect(self.scan_capabilities)
        self.settings_view.cancel_scan.clicked.connect(self.model.cancel_capabilities)
        self.settings_view.gpu_device.textChanged.connect(self.model.invalidate_capabilities)
        self.mode.currentIndexChanged.connect(self.model.binary_selection_changed)
        self.folder.textChanged.connect(self.model.binary_selection_changed)
        self.choose_file_button.clicked.connect(self.choose_file)
        self.remux_button.clicked.connect(self.run_form)
        self.remux_view.cancel_button.clicked.connect(self.model.cancel_remux)
        self.remux_view.enqueue_button.clicked.connect(self.model.enqueue_remux)
        self.queue_view.save_definitions.clicked.connect(self.save_queue_definitions)
        self.queue_view.load_definitions.clicked.connect(self.load_queue_definitions)
        self.queue_view.cancel_direct.clicked.connect(self.model.cancel_remux)
        self.queue_view.open_output.clicked.connect(self.open_queue_output)
        self.queue_view.start_button.clicked.connect(self.model.start_queue)
        self.queue_view.cancel_button.clicked.connect(self.cancel_queue_selected)
        self.queue_view.cancel_all_button.clicked.connect(self.model.queue.cancel_all)
        self.queue_view.retry_button.clicked.connect(self.retry_queue_selected)
        self.queue_view.cpu_retry_button.clicked.connect(self.retry_queue_cpu)
        self.queue_view.table.selectionModel().selectionChanged.connect(self.render_queue_details)
        self.remux_view.metadata_policy.currentIndexChanged.connect(self.preservation_changed)
        self.remux_view.chapter_policy.currentIndexChanged.connect(self.preservation_changed)
        self.remux_view.browse_button.clicked.connect(self.choose_remux_destination)
        self.remux_view.destination.textChanged.connect(self.output_changed)
        self.container.currentIndexChanged.connect(self.container_changed)
        self.remux_view.preview_button.clicked.connect(self.model.preview)
        self.files_view.files_dropped.connect(self.import_media)
        self.files_view.streams_selected.connect(self.model.select_streams)
        self.remux_view.streams_selected.connect(self.model.select_streams)
        self.files_view.inspect_button.clicked.connect(self.inspect_current)
        self.files_view.inspect_selected_button.clicked.connect(self.inspect_selected)
        self.files_view.cancel_button.clicked.connect(self.model.cancel_inspection)
        self.files_view.clear_button.clicked.connect(self.model.clear_files)
        self.files_view.file_list.selectionModel().currentChanged.connect(lambda current, previous: self.select_current(current.row()))
        self.files_view.file_list.selectionModel().selectionChanged.connect(self.file_selection_changed)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setAccessibleName('Operation feedback and technical details')
        self.output.setPlaceholderText('Operation results and details will appear here.')
        self.workspace = Workspace(self, layout_settings)
        layout.addWidget(self.workspace)

        self._preview_view = self.convert_view
        self.convert_view.preview_button.clicked.connect(self.preview_convert)
        self.convert_view.run_button.clicked.connect(self.run_convert)
        self.convert_view.enqueue_button.clicked.connect(self.enqueue_convert)
        self.convert_view.browse.clicked.connect(self.browse_convert)
        self.compress_view.preview_button.clicked.connect(self.preview_convert)
        self.compress_view.run_button.clicked.connect(self.run_convert)
        self.compress_view.enqueue_button.clicked.connect(self.enqueue_convert)
        self.compress_view.browse.clicked.connect(self.browse_convert)
        for view in (self.convert_view, self.compress_view):
            view.batch_button.clicked.connect(self.enqueue_encoding_batch)
            view.import_profile_button.clicked.connect(self.import_encoding_profile)
            view.export_profile_button.clicked.connect(self.export_encoding_profile)
        self.model.profile_loaded.connect(self.apply_imported_profile)
        self.model.encoding_preview_ready.connect(self.show_encoding_preview)
        self._capability_display_key = None
        self.model.changed.connect(self.render)
        self.configure_shortcuts()
        self.render()
        self.detect()

    def configure_shortcuts(self) -> None:
        from PySide6.QtGui import QShortcut
        shortcuts = {'Ctrl+O': self.choose_file, 'Ctrl+Shift+L': self.workspace.reset_layout,
                     'Ctrl+Return': self.model.start_queue}
        for key, callback in shortcuts.items():
            QShortcut(key, self, activated=callback)
        for index in range(6):
            QShortcut(f'Alt+{index + 1}', self,
                      activated=lambda index=index: self.navigation.setCurrentRow(index))
        self.workspace.import_button.setToolTip('Import local media (Ctrl+O)')
        self.queue_view.start_button.setToolTip('Start pending tasks (Ctrl+Enter)')
        self.navigation.setToolTip('Modes: Alt+1 through Alt+6')

    # Read-only lifecycle access for the shell's shutdown policy and diagnostics.
    @property
    def thread(self) -> QThread | None:
        return self.model.thread

    @property
    def remux_task(self) -> RemuxTask | OperationTask | None:
        return self.model.remux_task

    @property
    def binaries(self) -> Binaries | None:
        return self.model.state.binaries

    @property
    def source(self) -> Path | None:
        return self.model.state.source

    @Slot()
    def render(self) -> None:
        state = self.model.state
        self.status.setText(state.status)
        self.workspace.import_button.setEnabled(not state.busy and state.binaries is not None)
        self.workspace.source.setText(str(state.current_file) if state.current_file else 'No source selected')
        self.activity.set_status('Working' if state.busy else 'Ready', 'loading' if state.busy else 'neutral')
        active = [r for r in self.model.queue.records if r.status in (TaskStatus.PREPARING, TaskStatus.RUNNING)]
        codecs = ', '.join(dict.fromkeys(s.profile.encoder for r in active for s in r.plan.streams))
        self.binary_summary.setText(('FFmpeg ready' if state.binaries else 'FFmpeg unavailable — open Settings') +
                                    f' · {len(active) + int(self.model.remux_task is not None)} active' +
                                    (f' · {codecs}' if codecs else ''))
        self.binary_summary.setToolTip(state.status)
        self.files_view.empty_state.setVisible(not state.files)
        self.files_view.file_list.setVisible(bool(state.files))
        self.convert_view.set_media(state.media, state.busy)
        self.compress_view.set_media(state.media, state.busy)
        for view in (self.convert_view, self.compress_view):
            view.set_capabilities(self.model.capabilities)
        settings = self.settings_view
        settings.export_diagnostics.setEnabled(not state.busy)
        settings.sidecar_button.setEnabled(not state.busy)
        settings.scan_button.setEnabled(not state.busy and state.binaries is not None)
        settings.cancel_scan.setEnabled(self.model.capability_active)
        settings.test_gpu.setEnabled(not state.busy)
        settings.gpu_device.setEnabled(not state.busy)
        report = self.model.capabilities
        key = (id(report), self.model.capability_active)
        if key != self._capability_display_key:
            self._capability_display_key = key
            capability_text = 'Scanning…' if self.model.capability_active and report is None else 'Scan the selected FFmpeg build to inspect capabilities.'
            if report is not None:
                capability_text = f'Selected FFmpeg: {report.build.identity[0]}\n'
                capability_text += '\n'.join(f'{c.name}: {c.status.value}' for c in report.gpu)
                capability_text += '\n\nBuild details:\n' + report.build.version + '\n' + report.build.configuration
                capability_text += '\nHardware APIs listed: ' + ', '.join(report.build.hwaccels)
                capability_text += '\nEncoders listed: ' + ', '.join(sorted(report.build.encoders))
                for capability in report.gpu:
                    capability_text += f'\n\n{capability.name}: {capability.status.value}\n{capability.detail}'
                for name, help_text in report.build.encoder_help:
                    capability_text += f'\n\n{name} help:\n{help_text}'
            if settings.capabilities.toPlainText() != capability_text:
                settings.capabilities.setPlainText(capability_text)
        self.workspace.media_timeline.set_media(state.media)
        self.workspace.playback.set_source(state.media.path if state.media else None)
        self.files_view.set_media(state.media, state.selected_streams)
        self.remux_view.set_tracks(state.media, state.selected_streams)
        self.remux_view.tracks.setEnabled(not state.busy)
        self.remux_view.metadata_policy.setEnabled(not state.busy)
        self.remux_view.chapter_policy.setEnabled(not state.busy)
        self.remux_view.cancel_button.setEnabled(self.model.remux_task is not None)
        self.remux_view.progress_label.setText(state.remux_progress)
        self.files_view.stream_table.setEnabled(not state.busy)
        listing = self.files_view.file_list
        had_current = listing.currentIndex().isValid()
        with QSignalBlocker(listing.selectionModel()):
            self.files_view.media_model.update(state.files, state.inspections)
            if state.current_file in state.files:
                index = self.files_view.media_model.index(state.files.index(state.current_file))
                if listing.currentIndex() != index:
                    listing.selectionModel().setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate if had_current else QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.file_selection_changed()
        self.files_view.cancel_button.setEnabled(state.inspection_active and not state.cancel_requested)
        self.files_view.batch_status.setText(state.inspection_summary)
        listing.setEnabled(not state.busy)
        self.files_view.setAcceptDrops(not state.busy)
        self.files_view.inspect_button.setEnabled(not state.busy and state.binaries is not None and state.current_file is not None)
        self.files_view.clear_button.setEnabled(not state.busy and bool(state.files))
        if self.output.toPlainText() != state.output:
            self.output.setPlainText(state.output)
        self.detect_button.setEnabled(not state.busy)
        self.choose_file_button.setEnabled(not state.busy and state.binaries is not None)
        self.remux_button.setEnabled(not state.busy and not state.form_error)
        self.remux_view.enqueue_button.setEnabled(not state.busy and not state.form_error)
        self.render_queue()
        self.remux_view.preview_button.setEnabled(not state.busy and not state.form_error)
        self.remux_view.browse_button.setEnabled(not state.busy and state.source is not None)
        self.remux_view.destination.setEnabled(not state.busy)
        invalid = bool(state.source and state.destination.strip() and state.form_error)
        for field in (self.remux_view.validation, self.remux_view.destination):
            validation = 'error' if invalid else ''
            if field.property('validation') != validation:
                field.setProperty('validation', validation)
                field.style().unpolish(field)
                field.style().polish(field)
        self.remux_view.validation.setText(state.form_error or 'Ready. Selected streams will be validated before execution.')
        with QSignalBlocker(self.remux_view.destination):
            self.remux_view.destination.setText(state.destination)
        with QSignalBlocker(self.container):
            self.container.setCurrentIndex(self.container.findData(state.container))
        self.remux_view.preview.setPlainText(json.dumps(state.command, ensure_ascii=False, indent=2) if state.command else '')
        self.remux_view.source_label.setText(f'Source: {state.source}' if state.source else 'Inspect a file first.')
        for widget in (self.mode, self.folder, self.settings_view.browse_button, self.container):
            widget.setEnabled(not state.busy)

    @Slot()
    def select_sidecar(self) -> None:
        from media_wrapper.infrastructure.ffmpeg.binary_resolver import (
            sidecar_directory,
        )
        self.mode.setCurrentText('bundled')
        self.folder.setText(str(sidecar_directory()))
        self.detect()

    @Slot()
    def scan_capabilities(self) -> None:
        self.model.scan_capabilities(self.settings_view.test_gpu.isChecked(), self.settings_view.gpu_device.text().strip() or None)

    def encoding_sender(self) -> EncodingView:
        view = self.compress_view
        return view if self.sender() in (view.preview_button, view.run_button, view.enqueue_button, view.browse, view.import_profile_button, view.export_profile_button, view.batch_button) else self.convert_view

    @Slot()
    def preview_convert(self) -> None:
        self.encoding_action(self.encoding_sender(), 'preview')

    @Slot()
    def run_convert(self) -> None:
        self.encoding_action(self.encoding_sender(), 'run')

    @Slot()
    def enqueue_convert(self) -> None:
        self.encoding_action(self.encoding_sender(), 'enqueue')

    @Slot()
    def browse_convert(self) -> None:
        self.choose_encoding_destination(self.encoding_sender())

    @Slot()
    def enqueue_encoding_batch(self) -> None:
        view = self.encoding_sender()
        try:
            request = view.request()
        except ValueError as error:
            self.model.state.output = str(error)
            self.render()
            return
        paths = tuple(Path(item.data(Qt.ItemDataRole.UserRole)) for item in self.files_view.file_list.selectionModel().selectedIndexes())
        folder = Path(view.batch_folder.text()) if view.batch_folder.text().strip() else request.destination.parent
        self.model.enqueue_batch(paths, request, folder, view.batch_template.text())

    @Slot()
    def import_encoding_profile(self) -> None:
        self.exchange_encoding_profile(True)

    @Slot()
    def export_encoding_profile(self) -> None:
        self.exchange_encoding_profile(False)

    def exchange_encoding_profile(self, importing: bool) -> None:
        view = self.encoding_sender()
        try:
            request = view.request()
        except ValueError as error:
            self.model.state.output = str(error)
            self.render()
            return
        name, _ = (QFileDialog.getOpenFileName(self, 'Import profile', '', 'JSON (*.json)') if importing else
                   QFileDialog.getSaveFileName(self, 'Save profile as a new file', '', 'JSON (*.json)'))
        if name:
            self._preview_view = view
            self.model.exchange_profile(Path(name), request, importing)

    @Slot(object)
    def apply_imported_profile(self, request: object) -> None:
        from media_wrapper.domain.operations import MediaOperation
        self._preview_view = self.compress_view if request.operation == MediaOperation.COMPRESS else self.convert_view
        self._preview_view.apply_request(request)
        self.navigation.setCurrentRow(3 if request.operation == MediaOperation.COMPRESS else 2)
        self.model.state.output = 'Profile validated against the selected build and applied. Review choices before running.'
        self.render()

    def encoding_action(self, view: EncodingView, action: str) -> None:
        try:
            request = view.request()
        except ValueError as error:
            self.model.state.output = str(error)
            self.render()
            return
        self._preview_view = view
        self.model.encode(request, action)
        if action == 'run' and self.model.queue.running:
            self.navigation.setCurrentRow(4)

    def show_encoding_preview(self, command: list[list[str]]) -> None:
        self._preview_view.advanced_toggle.setChecked(True)
        self._preview_view.preview.setPlainText(json.dumps(command, ensure_ascii=False, indent=2))
        self.model.state.output = 'Validated preview. Run creates a fresh temporary path; executed arguments are shown in Queue.'
        self.render()

    def choose_encoding_destination(self, view: EncodingView) -> None:
        suffix = CONTAINERS[Container(view.container.currentData())].extension
        name, _ = QFileDialog.getSaveFileName(self, 'Choose new output', view.destination.text(), f'Media (*{suffix})')
        if name:
            view.destination.setText(name)

    def render_queue(self) -> None:
        queue = self.model.queue
        direct = self.model.remux_task is not None
        self.queue_view.direct_status.setVisible(direct)
        self.queue_view.cancel_direct.setVisible(direct)
        self.queue_view.direct_status.setText('Direct Remux · ' + (self.model.state.remux_progress or 'Preparing'))
        table = self.queue_view.table
        self.queue_view.empty_state.setVisible(not queue.records)
        table.setVisible(bool(queue.records))
        self.queue_view.details.setVisible(bool(queue.records) and self.queue_view.details_toggle.isChecked())
        row = table.currentIndex().row()
        with QSignalBlocker(table.selectionModel()):
            self.queue_view.task_model.update(queue.records)
            if queue.records and not table.currentIndex().isValid():
                table.selectRow(max(0, min(row, len(queue.records) - 1)))
        self.queue_view.save_definitions.setEnabled(not self.model.state.busy and any(r.status != TaskStatus.COMPLETED for r in queue.records))
        self.queue_view.load_definitions.setEnabled(not self.model.state.busy and self.binaries is not None)
        self.queue_view.start_button.setEnabled(not self.model.state.busy and any(r.status == TaskStatus.PENDING for r in queue.records))
        self.queue_view.cancel_all_button.setEnabled(any(r.status in (TaskStatus.PENDING, TaskStatus.PREPARING, TaskStatus.RUNNING) for r in queue.records))
        self.render_queue_details()

    def render_queue_details(self) -> None:
        row = self.queue_view.table.currentIndex().row()
        records = self.model.queue.records
        record = records[row] if 0 <= row < len(records) else None
        self.queue_view.cancel_button.setEnabled(record is not None and record.status in (TaskStatus.PENDING, TaskStatus.PREPARING, TaskStatus.RUNNING))
        self.queue_view.retry_button.setEnabled(record is not None and record.status in (TaskStatus.FAILED, TaskStatus.CANCELLED))
        self.queue_view.cpu_retry_button.setEnabled(record is not None and record.status in (TaskStatus.FAILED, TaskStatus.CANCELLED) and any(s.profile.encoder in GPU_ENCODERS for s in record.plan.streams))
        self.queue_view.open_output.setEnabled(record is not None and record.status == TaskStatus.COMPLETED and record.result is not None)
        if record is None:
            self.queue_view.details.clear()
            return
        progress = record.progress
        text = (f'{record.status.value}\nOutput: {record.plan.output.path}\n'
                f'Temporary path (may remain): {record.partial_path or "not created"}\n'
                f'Estimated speed: {progress.speed}; ETA: {progress.eta} seconds\n'
                f'{record.error}\nArguments: {json.dumps(record.command, ensure_ascii=False)}\n')
        if record.result is not None:
            text += 'Verified output:\n' + format_inspection(record.result)
        self.queue_view.details.setPlainText(text + '\nDiagnostics (last 16000 characters):\n' + record.log)

    def open_queue_output(self) -> None:
        row = self.queue_view.table.currentIndex().row()
        records = self.model.queue.records
        if 0 <= row < len(records) and records[row].status == TaskStatus.COMPLETED and records[row].result is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(records[row].plan.output.path.parent)))

    def cancel_queue_selected(self) -> None:
        row = self.queue_view.table.currentIndex().row()
        if 0 <= row < len(self.model.queue.records):
            self.model.queue.cancel(self.model.queue.records[row].id)

    def retry_queue_selected(self) -> None:
        row = self.queue_view.table.currentIndex().row()
        if 0 <= row < len(self.model.queue.records):
            record = self.model.queue.records[row]
            if record.status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                self.model.queue.retry(record.id)

    def retry_queue_cpu(self) -> None:
        row = self.queue_view.table.currentIndex().row()
        if 0 <= row < len(self.model.queue.records):
            record = self.model.queue.records[row]
            if record.status in (TaskStatus.FAILED, TaskStatus.CANCELLED) and any(s.profile.encoder in GPU_ENCODERS for s in record.plan.streams):
                self.model.queue.retry_cpu(record.id)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, 'Select directory with ffmpeg and ffprobe')
        if folder:
            self.folder.setText(folder)

    def detect(self) -> None:
        self.model.detect(self.mode.currentText(), self.folder.text().strip() or None)

    def choose_file(self) -> None:
        if self.model.state.busy or self.binaries is None:
            return
        names, _ = QFileDialog.getOpenFileNames(self, 'Select media files')
        self.import_media([Path(name) for name in names])

    def import_media(self, paths: list[Path]) -> None:
        if self.model.state.busy:
            return
        self.model.add_files(paths)
        pending = tuple(p for p in paths if p in self.model.state.files)
        if pending and self.binaries is not None:
            self.model.inspect_many(pending)

    def select_current(self, row: int) -> None:
        self.model.select_file(self.model.state.files[row] if 0 <= row < len(self.model.state.files) else None)

    def inspect_current(self) -> None:
        if self.model.state.current_file is not None:
            self.run_inspection(self.model.state.current_file)

    def file_selection_changed(self) -> None:
        self.files_view.inspect_selected_button.setEnabled(not self.model.state.busy and self.binaries is not None
                                                          and bool(self.files_view.file_list.selectionModel().selectedIndexes()))

    def inspect_selected(self) -> None:
        paths = tuple(Path(item.data(Qt.ItemDataRole.UserRole)) for item in self.files_view.file_list.selectionModel().selectedIndexes())
        self.model.inspect_many(paths)

    def run_inspection(self, path: Path) -> None:
        self.model.inspect(path)

    def choose_remux_destination(self) -> None:
        if self.source is None or self.model.state.busy:
            return
        container = Container(self.container.currentData())
        suffix = CONTAINERS[container].extension
        name, _ = QFileDialog.getSaveFileName(self, 'Save remux as a new file',
                                             str((self.model.state.recent_destination or self.source.parent) / (self.source.stem + '_remux' + suffix)),
                                             f'Media (*{suffix})')
        if name:
            self.model.state.recent_destination = Path(name).parent
            self.model.set_output(name, container)

    def preservation_changed(self) -> None:
        self.model.set_preservation(PreservationPolicy(self.remux_view.metadata_policy.currentText()),
                                    PreservationPolicy(self.remux_view.chapter_policy.currentText()))

    def container_changed(self) -> None:
        from media_wrapper.ui.output_paths import suggest_output_path
        container = Container(self.container.currentData())
        destination = suggest_output_path(self.remux_view.destination.text(), container)
        self.model.set_output(destination, container)

    def output_changed(self) -> None:
        container = Container(self.container.currentData())
        self.model.set_output(self.remux_view.destination.text(), container)

    def run_form(self) -> None:
        if not self.model.state.form_error:
            self.run_remux(Path(self.model.state.destination), self.model.state.container)

    def run_remux(self, destination: Path, container: Container) -> None:
        self.model.remux(destination, container)

    def start_remux(self, command: list[str]) -> None:
        self.model.start_remux(command)

    def save_queue_definitions(self) -> None:
        self.exchange_queue_definitions(False)

    def load_queue_definitions(self) -> None:
        self.exchange_queue_definitions(True)

    def exchange_queue_definitions(self, importing: bool) -> None:
        name, _ = (QFileDialog.getOpenFileName(self, 'Load queue definitions', '', 'JSON (*.json)') if importing else
                   QFileDialog.getSaveFileName(self, 'Save queue definitions (contains local paths)', '', 'JSON (*.json)'))
        if name:
            self.model.exchange_queue(Path(name), importing)

    def export_diagnostics(self) -> None:
        name, _ = QFileDialog.getSaveFileName(self, 'Export diagnostics to a new file', '', 'JSON (*.json)')
        if name:
            self.model.export_diagnostics(Path(name), self.settings_view.private_diagnostics.isChecked())

    def preferences(self) -> Preferences:
        return Preferences(log_level=self.settings_view.log_level.currentText(), binary_mode=self.mode.currentText(), binary_directory=self.folder.text(),
                           recent_destination=str(self.model.state.recent_destination) if self.model.state.recent_destination else None,
                           container=self.model.state.container.value,
                           advanced=self.remux_view.advanced_toggle.isChecked(), page=self.pages.currentIndex(),
                           width=min(8192, max(640, self.width())), height=min(8192, max(480, self.height())))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.model.state.busy:
            QMessageBox.information(self, 'Operation running',
                                    'Cancel inspection or allow it to finish before closing.' if self.model.state.inspection_active else
                                    'Cancel the operation or allow it to finish before closing.')
            event.ignore()
            return
        self.workspace.playback.shutdown()
        self.workspace.save_layout()
        if self.settings_service:
            warning = self.settings_service.save(self.preferences())
            if warning:
                QMessageBox.warning(self, 'Preferences not saved', warning)
        super().closeEvent(event)
