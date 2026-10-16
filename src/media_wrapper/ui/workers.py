"""Background adapters for application services."""
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from media_wrapper.application.binary_service import detect_binaries
from media_wrapper.application.errors import report_failure
from media_wrapper.application.media_service import MediaService
from media_wrapper.domain.remux import Container


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


