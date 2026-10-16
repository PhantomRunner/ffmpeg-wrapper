"""Background adapters for application services."""
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from media_wrapper.application.binary_service import detect_binaries
from media_wrapper.application.conversion_service import preview_conversion
from media_wrapper.application.errors import report_failure
from media_wrapper.application.inspection_batch import InspectionBatch
from media_wrapper.application.media_service import MediaService
from media_wrapper.domain.operations import OperationPlan
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
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(object)

    def __init__(self, service: MediaService, paths: tuple[Path, ...], cancel_event: Event) -> None:
        super().__init__()
        self.service, self.paths, self.cancel_event = service, paths, cancel_event

    @Slot()
    def run(self) -> None:
        try:
            results = InspectionBatch(self.service).run(self.paths, self.cancel_event, self.progress.emit)
            self.finished.emit(results)
        except Exception as exc:  # noqa: BLE001 - report orchestration failures across the Qt worker boundary
            self.failed.emit(report_failure('Inspection', exc))


class RemuxPreparationWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, service: MediaService, source: Path, destination: Path, container: Container, indices: tuple[int, ...] | None = None) -> None:
        super().__init__()
        self.service, self.source = service, source
        self.destination, self.container = destination, container
        self.indices = indices

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self.service.prepare_remux(self.source, self.destination, self.container, self.indices))
        except Exception as exc:  # noqa: BLE001 - report failures across the Qt worker boundary
            self.failed.emit(report_failure('Remux preparation', exc))




class EncodingPreviewWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, binaries: 'Binaries', plan: 'OperationPlan') -> None:
        super().__init__()
        self.binaries, self.plan = binaries, plan

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(preview_conversion(self.binaries, self.plan))
        except Exception as exc:  # noqa: BLE001 - worker boundary
            self.failed.emit(report_failure('Conversion preview', exc))
