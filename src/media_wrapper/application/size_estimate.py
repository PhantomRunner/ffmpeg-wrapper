"""Fast, filesystem-free estimates using the same target-size policy as execution."""
import math

from media_wrapper.application.conversion_service import conversion_plan
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.target_size import apply_target_size


def estimate_output(media: MediaFile, request: ConversionRequest) -> str:
    if request.mode in ('quality', 'default'):
        return 'Size varies with content and quality; no reliable estimate before encoding.'
    duration = media.duration
    if duration is None or not math.isfinite(duration) or duration <= 0:
        return 'Estimate unavailable: source duration is unknown.'
    plan = apply_target_size(conversion_plan(media, request))
    sources = {stream.index: stream for stream in media.streams}
    total = 0
    for selection in plan.streams:
        source, profile = sources[selection.index], selection.profile
        rate = source.bit_rate if profile.encoder == 'copy' else profile.bitrate
        if source.kind not in ('video', 'audio') or rate is None or rate <= 0:
            return 'Estimate unavailable: every selected stream needs a known bitrate.'
        total += rate
    if not plan.streams:
        return 'Select at least one stream for an estimate.'
    size = total * duration / 8 / .98 / 1048576
    result = f'Estimated output: {size:.1f} MiB (2% muxing reserve; actual size may differ).'
    if plan.two_pass:
        video = next(s for s in plan.streams if sources[s.index].kind == 'video')
        result += f' Two-pass video: {video.profile.bitrate / 1000:.0f} kb/s.'
    return result
