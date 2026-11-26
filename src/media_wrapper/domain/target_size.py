"""Strict limits and conservative bitrate planning for two-pass H.264."""
import math
from dataclasses import replace
from decimal import Decimal, InvalidOperation

from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import (
    OperationPlan,
    PlanValidationError,
    ValidationCode,
)

SIZE_UNITS = ('MB', 'MiB', 'MB/min', 'MiB/min', '%')
MIN_VIDEO_RATE = 32_000
MUX_HEADROOM = 0.02


def size_limit(value: str, unit: str, media: MediaFile) -> int:
    """Normalize a requested maximum to whole bytes, rounding down."""
    try:
        if not isinstance(value, str) or len(value) > 32:
            raise InvalidOperation
        amount = Decimal(value.strip())
    except InvalidOperation as error:
        raise ValueError('Specify a positive number for the size limit') from error
    if unit not in SIZE_UNITS or not amount.is_finite() or amount <= 0:
        raise ValueError('Specify a positive limit in MB, MiB, MB/min, MiB/min or %')
    if unit == '%':
        if amount >= 100 or not media.size_bytes:
            raise ValueError('Percentage reduction requires a known source size and a value below 100')
        cap = media.size_bytes * (1 - amount / 100)
    else:
        cap = amount * (1_000_000 if unit.startswith('MB') else 1_048_576)
        if unit.endswith('/min'):
            if media.duration is None or not math.isfinite(media.duration) or media.duration <= 0:
                raise ValueError('Size per minute requires a known positive duration')
            cap = cap * Decimal(str(media.duration)) / 60
    if not 1 <= cap <= 2**63 - 1:
        raise ValueError('Requested size is outside the supported range')
    return int(cap)


def _audio_rate(plan: OperationPlan) -> int:
    sources = {s.index: s for s in plan.media.streams}
    audio_rate = 0
    for selection in plan.streams:
        stream = sources.get(selection.index)
        if stream is None:
            raise PlanValidationError(ValidationCode.STREAM, 'Target size references a missing stream')
        if stream.kind == 'video' and not stream.is_artwork:
            continue
        if stream.kind != 'audio':
            raise PlanValidationError(ValidationCode.OPTION, 'Target size requires measurable video/audio streams')
        rate = stream.bit_rate if selection.profile.encoder == 'copy' else selection.profile.bitrate
        if rate is None or rate <= 0 or selection.profile.audio_quality is not None:
            raise PlanValidationError(ValidationCode.OPTION, 'Target size needs known audio bitrates; choose an audio bitrate or remove the track')
        audio_rate += rate
    return audio_rate


def _set_video_rate(plan: OperationPlan, rate: int) -> OperationPlan:
    return replace(plan, streams=tuple(
        replace(s, profile=replace(s.profile, bitrate=rate, crf=None)) if s.profile.encoder == 'libx264' else s
        for s in plan.streams
    ), two_pass=True)


def apply_target_size(plan: OperationPlan) -> OperationPlan:
    if plan.target_size_bytes is None:
        return plan
    duration, cap = plan.media.duration, plan.target_size_bytes
    if duration is None or not math.isfinite(duration) or duration <= 0:
        raise PlanValidationError(ValidationCode.OPTION, 'Target size needs a known positive duration')
    if type(cap) is not int or cap <= 0:
        raise PlanValidationError(ValidationCode.OPTION, 'Target size must be a positive byte count')
    rate = int(cap * 8 * (1 - MUX_HEADROOM) / duration - _audio_rate(plan))
    source = {s.index: s for s in plan.media.streams}
    video = [s for s in plan.streams if source[s.index].kind == 'video']
    if len(video) != 1 or video[0].profile.encoder != 'libx264':
        raise PlanValidationError(ValidationCode.OPTION, 'Target size requires libx264 two-pass encoding and exactly one selected video')
    if rate < MIN_VIDEO_RATE:
        raise PlanValidationError(ValidationCode.OPTION, 'Target size is too small for the duration and audio bitrate')
    return _set_video_rate(plan, rate)


def tighten_target_size(plan: OperationPlan, actual_bytes: int) -> OperationPlan | None:
    """Lower only the video bitrate after observing an oversized staged output."""
    cap, duration = plan.target_size_bytes, plan.media.duration
    if cap is None or duration is None or actual_bytes <= cap:
        return None
    selection = next(s for s in plan.streams if s.profile.encoder == 'libx264')
    rate = selection.profile.bitrate
    if rate is None or rate <= MIN_VIDEO_RATE:
        return None
    fixed = _audio_rate(plan) * duration / 8
    if actual_bytes <= fixed or cap <= fixed:
        return None
    ratio = (cap - fixed) / (actual_bytes - fixed) * 0.97
    return _set_video_rate(plan, max(MIN_VIDEO_RATE, min(rate - 1, int(rate * ratio))))
