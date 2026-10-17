"""Profile validation against current media and selected FFmpeg build; worker-only."""
from pathlib import Path
from threading import Event

from media_wrapper.application.conversion_service import conversion_plan
from media_wrapper.domain.capabilities import CapabilityReport
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operation_policy import validate_plan
from media_wrapper.domain.profile_document import parse_profile, profile_payload
from media_wrapper.domain.target_size import apply_target_size
from media_wrapper.infrastructure.ffmpeg.binary_resolver import Binaries
from media_wrapper.infrastructure.ffmpeg.encoders import list_encoders
from media_wrapper.infrastructure.json_documents import read_document, write_document


def validate_profile(request: ConversionRequest, media: MediaFile, binaries: Binaries,
                     report: CapabilityReport | None) -> None:
    if request.gpu_encoder != 'auto' and (report is None or request.gpu_encoder not in report.working()):
        raise ValueError('Profile GPU preference requires a successful current runtime scan')
    plan = apply_target_size(conversion_plan(media, request, report))
    validate_plan(plan, list_encoders(binaries.ffmpeg, Event()))


def import_profile(path: Path, destination: Path, media: MediaFile, binaries: Binaries,
                   report: CapabilityReport | None) -> ConversionRequest:
    request = parse_profile(read_document(path), destination)
    # A stored real index must match this source; no automatic track substitution.
    known = {s.index for s in media.streams}
    if any(i not in known for i, _ in request.tracks):
        raise ValueError('Profile refers to tracks absent from this source')
    validate_profile(request, media, binaries, report)
    return request


def export_profile(path: Path, request: ConversionRequest, media: MediaFile,
                   binaries: Binaries, report: CapabilityReport | None) -> Path:
    payload = profile_payload(request)
    parse_profile(payload, request.destination)
    validate_profile(request, media, binaries, report)
    write_document(path, payload)
    return path
