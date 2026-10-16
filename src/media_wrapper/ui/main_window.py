"""Qt Widgets frontend for binary detection, inspection and remux."""
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.application.binary_service import detect_binaries
from media_wrapper.application.errors import report_failure
from media_wrapper.application.media_service import MediaService
from media_wrapper.application.remux_task import RemuxTask
from media_wrapper.domain.remux import Container
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries


class DetectionWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, mode: str, directory: str | Path | None) -> None:
        super().__init__()
        self.mode, self.directory = mode, directory

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(detect_binaries(self.mode, self.directory))
        except Exception as exc:  # noqa: BLE001 - report failures across the Qt worker boundary
            self.failed.emit(report_failure('Binary detection', exc))


class InspectionWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, service: MediaService, path: Path) -> None:
        super().__init__()
        self.service, self.path = service, path

    @Slot()
    def run(self) -> None:
        try:
            info = self.service.inspect(self.path)
            lines = [f"File: {info.path}", f"Container: {info.format_name}",
                     f"Duration: {info.duration if info.duration is not None else 'unknown'} s",
                     f"Size: {info.size_bytes if info.size_bytes is not None else 'unknown'} bytes", ""]
            for i, stream in enumerate(info.streams):
                lines.append(f"Stream {i}: {stream.get('codec_type', '?')} / {stream.get('codec_name', '?')}")
                for key in ("width", "height", "sample_rate", "channels", "bit_rate"):
                    if key in stream:
                        lines.append(f"  {key}: {stream[key]}")
            self.finished.emit("\n".join(lines))
        except Exception as exc:  # noqa: BLE001 - report failures across the Qt worker boundary
            self.failed.emit(report_failure('Inspection', exc))


class RemuxPreparationWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, service: MediaService, source: Path, destination: Path, container: Container) -> None:
        super().__init__()
        self.service, self.source = service, source
        self.destination, self.container = destination, container

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self.service.prepare_remux(self.source, self.destination, self.container))
        except Exception as exc:  # noqa: BLE001 - report failures across the Qt worker boundary
            self.failed.emit(report_failure('Remux preparation', exc))


class MainWindow(QMainWindow):
    def __init__(self, diagnostic_status: str = '') -> None:
        super().__init__()
        self.setWindowTitle("Media Wrapper — FFmpeg UI")
        self.resize(850, 580)
        self.statusBar().showMessage(diagnostic_status)
        self.binaries: Binaries | None = None
        self.thread: QThread | None = None
        self.worker: DetectionWorker | InspectionWorker | RemuxPreparationWorker | None = None
        self.source: Path | None = None
        self.inspection_path: Path | None = None
        self.remux_task: RemuxTask | None = None
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        controls = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["external", "bundled"])
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Optional bin directory (external: empty = PATH)")
        browse = QPushButton("Browse bin folder")
        browse.clicked.connect(self.choose_folder)
        self.detect_button = QPushButton("Detect FFmpeg")
        self.detect_button.clicked.connect(self.detect)
        controls.addWidget(QLabel("Mode:"))
        controls.addWidget(self.mode)
        controls.addWidget(self.folder, 1)
        controls.addWidget(browse)
        controls.addWidget(self.detect_button)
        layout.addLayout(controls)
        self.status = QLabel("FFmpeg not detected")
        layout.addWidget(self.status)

        self.choose_file_button = QPushButton("Open media file and inspect")
        self.choose_file_button.setEnabled(False)
        self.choose_file_button.clicked.connect(self.choose_file)
        layout.addWidget(self.choose_file_button)
        remux_controls = QHBoxLayout()
        self.container = QComboBox()
        self.container.addItems(['Matroska (.mkv)', 'MP4 (.mp4)'])
        self.remux_button = QPushButton('Remux inspected file…')
        self.remux_button.setEnabled(False)
        self.remux_button.clicked.connect(self.choose_remux_destination)
        remux_controls.addWidget(self.container)
        remux_controls.addWidget(self.remux_button)
        layout.addLayout(remux_controls)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        self.detect()

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select directory with ffmpeg and ffprobe")
        if folder:
            self.folder.setText(folder)

    def detect(self) -> None:
        if self.thread is not None or self.remux_task is not None:
            return
        self.binaries = None
        self.source = None
        self.detect_button.setEnabled(False)
        self.choose_file_button.setEnabled(False)
        self.remux_button.setEnabled(False)
        self.status.setText('Detecting FFmpeg…')
        self.thread = QThread(self)
        self.worker = DetectionWorker(self.mode.currentText(), self.folder.text().strip() or None)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.detection_complete)
        self.worker.failed.connect(self.detection_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.cleanup_thread)
        self.thread.start()

    @Slot(object)
    def detection_complete(self, binaries: Binaries) -> None:
        self.binaries = binaries
        self.status.setText(f'Detected: {binaries.version}')

    @Slot(str)
    def detection_failed(self, error: str) -> None:
        self.status.setText(error)
        self.output.setPlainText(error)

    def choose_file(self) -> None:
        if not self.binaries or self.thread is not None or self.remux_task is not None:
            return
        name, _ = QFileDialog.getOpenFileName(self, "Select media file")
        if name:
            self.run_inspection(Path(name))

    def run_inspection(self, path: Path) -> None:
        if self.binaries is None or self.thread is not None or self.remux_task is not None:
            return
        self.source = None
        self.inspection_path = path
        self.remux_button.setEnabled(False)
        self.choose_file_button.setEnabled(False)
        self.detect_button.setEnabled(False)
        self.output.setPlainText("Inspecting…")
        self.thread = QThread(self)
        self.worker = InspectionWorker(MediaService(self.binaries), path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.output.setPlainText)
        self.worker.finished.connect(self.inspection_complete)
        self.worker.failed.connect(self.show_failure)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.cleanup_thread)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.thread.start()

    @Slot(str)
    def show_failure(self, error: str) -> None:
        self.output.setPlainText(error)

    def cleanup_thread(self) -> None:
        if self.thread is not None:
            self.thread.deleteLater()
        self.worker = None
        self.thread = None
        self.choose_file_button.setEnabled(self.binaries is not None and self.remux_task is None)
        self.detect_button.setEnabled(self.remux_task is None)
        self.remux_button.setEnabled(self.source is not None and self.remux_task is None)

    @Slot(str)
    def inspection_complete(self, _text: str) -> None:
        self.source = self.inspection_path

    def choose_remux_destination(self) -> None:
        if self.source is None or self.thread is not None or self.remux_task is not None:
            return
        container = [Container.MATROSKA, Container.MP4][self.container.currentIndex()]
        suffix = '.mkv' if container == Container.MATROSKA else '.mp4'
        name, _ = QFileDialog.getSaveFileName(self, 'Save remux as a new file',
                                             str(self.source.with_name(self.source.stem + '_remux' + suffix)),
                                             f'Media (*{suffix})')
        if name:
            self.run_remux(Path(name), container)

    def run_remux(self, destination: Path, container: Container) -> None:
        if self.source is None or self.binaries is None or self.thread is not None or self.remux_task is not None:
            return
        self.choose_file_button.setEnabled(False)
        self.detect_button.setEnabled(False)
        self.remux_button.setEnabled(False)
        self.output.setPlainText('Validating remux…')
        self.thread = QThread(self)
        self.worker = RemuxPreparationWorker(MediaService(self.binaries), self.source, destination, container)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.start_remux)
        self.worker.failed.connect(self.show_failure)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.cleanup_thread)
        self.thread.start()

    @Slot(object)
    def start_remux(self, command: list[str]) -> None:
        self.output.setPlainText('Remux running…')
        self.remux_task = RemuxTask(self)
        self.remux_task.finished.connect(self.remux_complete)
        self.remux_task.start(command)

    def remux_complete(self, success: bool, details: str) -> None:
        self.output.setPlainText('Remux complete.\n' + details if success else details)
        if self.remux_task is not None:
            self.remux_task.deleteLater()
        self.remux_task = None
        self.detect_button.setEnabled(self.thread is None)
        self.choose_file_button.setEnabled(self.thread is None and self.binaries is not None)
        self.remux_button.setEnabled(self.thread is None and self.source is not None)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.remux_task is not None or (self.thread is not None and self.thread.isRunning()):
            QMessageBox.information(self, "Operation running", "Allow the operation to finish before closing.")
            event.ignore()
            return
        super().closeEvent(event)
