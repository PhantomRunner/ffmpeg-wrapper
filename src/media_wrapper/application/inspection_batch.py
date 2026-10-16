"""Sequential inspection use case; Qt adapters supply progress callbacks."""
from collections.abc import Callable
from pathlib import Path
from threading import Event

from media_wrapper.application.errors import report_failure
from media_wrapper.application.media_service import MediaService
from media_wrapper.domain.inspection import (
    InspectionRecord,
    InspectionStatus,
    OperationCancelled,
)


class InspectionBatch:
    def __init__(self, service: MediaService) -> None:
        self.service = service

    def run(self, paths: tuple[Path, ...], cancel_event: Event,
            on_result: Callable[[InspectionRecord], None]) -> tuple[InspectionRecord, ...]:
        results = []
        for path in paths:
            if cancel_event.is_set():
                result = InspectionRecord(path, InspectionStatus.CANCELLED)
            else:
                on_result(InspectionRecord(path, InspectionStatus.RUNNING))
                try:
                    media = self.service.inspect(path, cancel_event=cancel_event)
                    result = InspectionRecord(path, InspectionStatus.CANCELLED) if cancel_event.is_set() else InspectionRecord(path, InspectionStatus.COMPLETED, media)
                except OperationCancelled:
                    cancel_event.set()
                    result = InspectionRecord(path, InspectionStatus.CANCELLED)
                except Exception as error:  # noqa: BLE001 - each file has an independent failure state
                    result = (InspectionRecord(path, InspectionStatus.CANCELLED) if cancel_event.is_set() else
                              InspectionRecord(path, InspectionStatus.FAILED, error=report_failure('Inspection', error)))
            results.append(result)
            on_result(result)
        return tuple(results)
