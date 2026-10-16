"""Desktop shell: page navigation and bindings to presentation state."""
import json
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QThread, Slot
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
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.ui.view_model import DesktopViewModel
from media_wrapper.ui.views import FilesView, PlaceholderView, RemuxView, SettingsView


class MainWindow(QMainWindow):
    def __init__(self, diagnostic_status: str = '') -> None:
        super().__init__()
        self.setWindowTitle('Media Wrapper — FFmpeg UI')
        self.resize(900, 650)
        self.statusBar().showMessage(diagnostic_status)
        self.model = DesktopViewModel(self)
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
        self.navigation.setCurrentRow(0)
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
        self.settings_view.browse_button.clicked.connect(self.choose_folder)
        self.detect_button.clicked.connect(self.detect)
        self.choose_file_button.clicked.connect(self.choose_file)
        self.remux_button.clicked.connect(self.run_form)
        self.remux_view.browse_button.clicked.connect(self.choose_remux_destination)
        self.remux_view.destination.textChanged.connect(self.output_changed)
        self.container.currentIndexChanged.connect(self.output_changed)
        self.remux_view.preview_button.clicked.connect(self.model.preview)
        self.files_view.files_dropped.connect(self.model.add_files)
        self.files_view.inspect_button.clicked.connect(self.inspect_current)
        self.files_view.clear_button.clicked.connect(self.model.clear_files)
        self.files_view.file_list.currentRowChanged.connect(self.select_current)
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
        listing = self.files_view.file_list
        paths = [str(path) for path in state.files]
        if [listing.item(i).text() for i in range(listing.count())] != paths:
            with QSignalBlocker(listing):
                listing.clear()
                listing.addItems(paths)
                if state.current_file in state.files:
                    listing.setCurrentRow(state.files.index(state.current_file))
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

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.model.state.busy:
            QMessageBox.information(self, 'Operation running', 'Allow the operation to finish before closing.')
            event.ignore()
            return
        super().closeEvent(event)
