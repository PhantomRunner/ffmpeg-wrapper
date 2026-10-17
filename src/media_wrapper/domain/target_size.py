"""Conservative target-size estimate for one H.264 video and known-rate audio."""
import math
from dataclasses import replace

from media_wrapper.domain.operations import (
    OperationPlan,
    PlanValidationError,
    ValidationCode,
)


def apply_target_size(plan: OperationPlan) -> OperationPlan:
    if plan.target_size_bytes is None:
        return plan
    def invalid(message: str) -> None:
        raise PlanValidationError(ValidationCode.OPTION, message)
    duration = plan.media.duration
    if duration is None or not math.isfinite(duration) or duration <= 0:
        invalid('Target size needs a known positive duration')
    if type(plan.target_size_bytes) is not int or plan.target_size_bytes <= 0:
        invalid('Target size must be a positive byte count')
    sources = {s.index: s for s in plan.media.streams}
    video = []
    audio_rate = 0
    for selection in plan.streams:
        stream = sources.get(selection.index)
        if stream is None:
            invalid('Target size references a missing stream')
        if stream.kind == 'video':
            if selection.profile.encoder != 'libx264':
                invalid('Target size currently requires libx264 two-pass video')
            video.append(selection)
        elif stream.kind == 'audio':
            rate = stream.bit_rate if selection.profile.encoder == 'copy' else selection.profile.bitrate
            if rate is None or rate <= 0 or selection.profile.audio_quality is not None:
                invalid('Target size needs known audio bitrates; choose AAC bitrate mode')
            audio_rate += rate
        else:
            invalid('Target-size mode supports video/audio only; omit other tracks')
    if len(video) != 1:
        invalid('Target size requires exactly one selected video track')
    # Reserve 2% for muxing. This is an estimate, never an exact size guarantee.
    bitrate = int(plan.target_size_bytes * 8 * .98 / duration - audio_rate)
    if bitrate < 32000:
        invalid('Target size is too small for the duration and audio bitrate')
    streams = tuple(replace(s, profile=replace(s.profile, bitrate=bitrate, crf=None)) if s is video[0] else s for s in plan.streams)
    return replace(plan, streams=streams, two_pass=True)
