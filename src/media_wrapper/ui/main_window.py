"""Desktop shell: page navigation and bindings to presentation state."""
import json
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSignalBlocker, Qt, QThread, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.application.remux_task import RemuxTask
from media_wrapper.application.settings_service import SettingsService
from media_wrapper.domain.preferences import Preferences
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.ui.view_model import DesktopViewModel
from media_wrapper.ui.views import FilesView, PlaceholderView, RemuxView, SettingsView


class MainWindow(QMainWindow):
    def __init__(self, diagnostic_status: str = '', settings_service: SettingsService | None = None) -> None:
        super().__init__()
        self.setWindowTitle('Media Wrapper — FFmpeg UI')
        self.settings_service = settings_service
        preferences = settings_service.load() if settings_service else Preferences()
        self.resize(preferences.width, preferences.height)
        self.setMinimumSize(640, 480)
        if settings_service and settings_service.warning:
            diagnostic_status += ' | ' + settings_service.warning
        self.statusBar().showMessage(diagnostic_status)
        self.model = DesktopViewModel(self)
        self.model.state.container = Container(preferences.container)
        self.model.state.recent_destination = Path(preferences.recent_destination) if preferences.recent_destination else None
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        pages = QHBoxLayout()
        self.navigation = QListWidget()
        self.navigation.addItems(['Files / Inspect', 'Remux', 'Convert', 'Compress', 'Queue', 'Settings'])
        self.navigation.setMaximumWidth(170)
        self.pages = QStackedWidget()
        self.files_view = FilesView()
        self.remux_view = RemuxView()
        self.settings_view = SettingsView()
        for page in (self.files_view, self.remux_view,
                     PlaceholderView('Convert', 'Transcoding controls will be added in a later milestone.'),
                     PlaceholderView('Compress', 'Compression controls will be added in a later milestone.'),
                     PlaceholderView('Queue', 'Task queue controls will be added in a later milestone.'),
                     self.settings_view):
            self.pages.addWidget(page)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(preferences.page)
        pages.addWidget(self.navigation)
        pages.addWidget(self.pages, 1)
        layout.addLayout(pages)
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
        self.detect_button.clicked.connect(self.detect)
        self.mode.currentIndexChanged.connect(self.model.binary_selection_changed)
        self.folder.textChanged.connect(self.model.binary_selection_changed)
        self.choose_file_button.clicked.connect(self.choose_file)
        self.remux_button.clicked.connect(self.run_form)
        self.remux_view.browse_button.clicked.connect(self.choose_remux_destination)
        self.remux_view.destination.textChanged.connect(self.output_changed)
        self.container.currentIndexChanged.connect(self.output_changed)
        self.remux_view.preview_button.clicked.connect(self.model.preview)
        self.files_view.files_dropped.connect(self.model.add_files)
        self.files_view.streams_selected.connect(self.model.select_streams)
        self.files_view.inspect_button.clicked.connect(self.inspect_current)
        self.files_view.inspect_selected_button.clicked.connect(self.inspect_selected)
        self.files_view.cancel_button.clicked.connect(self.model.cancel_inspection)
        self.files_view.clear_button.clicked.connect(self.model.clear_files)
        self.files_view.file_list.currentRowChanged.connect(self.select_current)
        self.files_view.file_list.itemSelectionChanged.connect(self.file_selection_changed)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        self.model.changed.connect(self.render)
        self.render()
        self.detect()

    # Read-only lifecycle access for the shell's shutdown policy and diagnostics.
    @property
    def thread(self) -> QThread | None:
        return self.model.thread

    @property
    def remux_task(self) -> RemuxTask | None:
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
        self.files_view.set_media(state.media, state.selected_streams)
        self.files_view.stream_table.setEnabled(not state.busy)
        listing = self.files_view.file_list
        paths = [str(path) for path in state.files]
        if [listing.item(i).data(Qt.ItemDataRole.UserRole) for i in range(listing.count())] != paths:
            with QSignalBlocker(listing):
                listing.clear()
                listing.addItems(paths)
                for row, path in enumerate(paths):
                    listing.item(row).setData(Qt.ItemDataRole.UserRole, path)
                if state.current_file in state.files:
                    listing.setCurrentRow(state.files.index(state.current_file))
        if state.current_file in state.files and listing.currentRow() != state.files.index(state.current_file):
            with QSignalBlocker(listing):
                listing.setCurrentRow(state.files.index(state.current_file), QItemSelectionModel.SelectionFlag.NoUpdate)
        for row, path in enumerate(state.files):
            record = state.inspections.get(path)
            status = record.status.value if record else 'Not inspected'
            listing.item(row).setText(f'{path} [{status}]')
            listing.item(row).setToolTip(record.error if record and record.error else status)
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
        self.remux_view.preview_button.setEnabled(not state.busy and not state.form_error)
        self.remux_view.browse_button.setEnabled(not state.busy and state.source is not None)
        self.remux_view.destination.setEnabled(not state.busy)
        self.remux_view.validation.setText(state.form_error or 'Ready. All streams will be validated before execution.')
        with QSignalBlocker(self.remux_view.destination):
            self.remux_view.destination.setText(state.destination)
        with QSignalBlocker(self.container):
            self.container.setCurrentIndex(0 if state.container == Container.MATROSKA else 1)
        self.remux_view.preview.setPlainText(json.dumps(state.command, ensure_ascii=False, indent=2) if state.command else '')
        self.remux_view.source_label.setText(f'Source: {state.source}' if state.source else 'Inspect a file first.')
        for widget in (self.mode, self.folder, self.settings_view.browse_button, self.container):
            widget.setEnabled(not state.busy)

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
        self.model.add_files([Path(name) for name in names])

    def select_current(self, row: int) -> None:
        self.model.select_file(self.model.state.files[row] if 0 <= row < len(self.model.state.files) else None)

    def inspect_current(self) -> None:
        if self.model.state.current_file is not None:
            self.run_inspection(self.model.state.current_file)

    def file_selection_changed(self) -> None:
        self.files_view.inspect_selected_button.setEnabled(not self.model.state.busy and self.binaries is not None
                                                          and bool(self.files_view.file_list.selectedItems()))

    def inspect_selected(self) -> None:
        paths = tuple(Path(item.data(Qt.ItemDataRole.UserRole)) for item in self.files_view.file_list.selectedItems())
        self.model.inspect_many(paths)

    def run_inspection(self, path: Path) -> None:
        self.model.inspect(path)

    def choose_remux_destination(self) -> None:
        if self.source is None or self.model.state.busy:
            return
        container = [Container.MATROSKA, Container.MP4][self.container.currentIndex()]
        suffix = '.mkv' if container == Container.MATROSKA else '.mp4'
        name, _ = QFileDialog.getSaveFileName(self, 'Save remux as a new file',
                                             str((self.model.state.recent_destination or self.source.parent) / (self.source.stem + '_remux' + suffix)),
                                             f'Media (*{suffix})')
        if name:
            self.model.state.recent_destination = Path(name).parent
            self.model.set_output(name, container)

    def output_changed(self) -> None:
        container = [Container.MATROSKA, Container.MP4][self.container.currentIndex()]
        self.model.set_output(self.remux_view.destination.text(), container)

    def run_form(self) -> None:
        if not self.model.state.form_error:
            self.run_remux(Path(self.model.state.destination), self.model.state.container)

    def run_remux(self, destination: Path, container: Container) -> None:
        self.model.remux(destination, container)

    def start_remux(self, command: list[str]) -> None:
        self.model.start_remux(command)

    def preferences(self) -> Preferences:
        return Preferences(binary_mode=self.mode.currentText(), binary_directory=self.folder.text(),
                           recent_destination=str(self.model.state.recent_destination) if self.model.state.recent_destination else None,
                           container=self.model.state.container.value,
                           advanced=self.remux_view.advanced_toggle.isChecked(), page=self.pages.currentIndex(),
                           width=min(8192, max(640, self.width())), height=min(8192, max(480, self.height())))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.model.state.busy:
            QMessageBox.information(self, 'Operation running',
                                    'Cancel inspection or allow it to finish before closing.' if self.model.state.inspection_active else
                                    'Allow the operation to finish before closing.')
            event.ignore()
            return
        if self.settings_service:
            warning = self.settings_service.save(self.preferences())
            if warning:
                QMessageBox.warning(self, 'Preferences not saved', warning)
        super().closeEvent(event)
