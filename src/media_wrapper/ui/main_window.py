"""Desktop shell: page navigation and bindings to presentation state."""
from pathlib import Path

from PySide6.QtCore import QThread, Slot
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
        self.remux_button.clicked.connect(self.choose_remux_destination)
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
        if self.output.toPlainText() != state.output:
            self.output.setPlainText(state.output)
        self.detect_button.setEnabled(not state.busy)
        self.choose_file_button.setEnabled(not state.busy and state.binaries is not None)
        self.remux_button.setEnabled(not state.busy and state.source is not None)
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
        name, _ = QFileDialog.getOpenFileName(self, 'Select media file')
        if name:
            self.run_inspection(Path(name))

    def run_inspection(self, path: Path) -> None:
        self.model.inspect(path)

    def choose_remux_destination(self) -> None:
        if self.source is None or self.model.state.busy:
            return
        container = [Container.MATROSKA, Container.MP4][self.container.currentIndex()]
        suffix = '.mkv' if container == Container.MATROSKA else '.mp4'
        name, _ = QFileDialog.getSaveFileName(self, 'Save remux as a new file',
                                             str(self.source.with_name(self.source.stem + '_remux' + suffix)),
                                             f'Media (*{suffix})')
        if name:
            self.run_remux(Path(name), container)

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
