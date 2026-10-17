"""Background adapters for application services."""
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from media_wrapper.application.binary_service import detect_binaries
from media_wrapper.application.conversion_service import preview_conversion
from media_wrapper.application.errors import report_failure
from media_wrapper.application.inspection_batch import InspectionBatch
from media_wrapper.application.media_service import MediaService
from media_wrapper.domain.operations import OperationPlan, PreservationPolicy
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

    def __init__(self, service: MediaService, source: Path, destination: Path, container: Container, indices: tuple[int, ...] | None = None, metadata_policy: PreservationPolicy = PreservationPolicy.PRESERVE, chapter_policy: PreservationPolicy = PreservationPolicy.PRESERVE) -> None:
        super().__init__()
        self.service, self.source = service, source
        self.destination, self.container = destination, container
        self.indices = indices
        self.metadata_policy, self.chapter_policy = metadata_policy, chapter_policy

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self.service.prepare_remux(self.source, self.destination, self.container, self.indices, self.metadata_policy, self.chapter_policy))
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


class CapabilityWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, binaries: Binaries, event: Event, test_gpu: bool, device: str | None) -> None:
        super().__init__()
        self.binaries, self.cancel_event, self.test_gpu, self.device = binaries, event, test_gpu, device

    @Slot()
    def run(self) -> None:
        from media_wrapper.application.capability_service import scan_capabilities
        from media_wrapper.domain.inspection import OperationCancelled
        try:
            self.finished.emit(scan_capabilities(self.binaries.ffmpeg, self.cancel_event, refresh=True,
                                                test_gpu=self.test_gpu, device=self.device))
        except OperationCancelled:
            self.failed.emit('Capability scan cancelled.')
        except Exception as exc:  # noqa: BLE001 - worker boundary
            self.failed.emit(report_failure('Capability scan', exc))


class ServiceWorker(QObject):
    """Short I/O/application work off the event loop, with the usual error boundary."""
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, action: 'Callable[[], Any]', operation: str) -> None:
        super().__init__()
        self.action, self.operation = action, operation

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self.action())
        except Exception as exc:  # noqa: BLE001 - worker boundary
            self.failed.emit(report_failure(self.operation, exc))
