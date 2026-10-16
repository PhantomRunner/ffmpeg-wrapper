"""Pure operation policy validation."""

from media_wrapper.domain.codec_policy import ALLOWED
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    PlanValidationError,
    ValidationCode,
)
from media_wrapper.domain.remux import Container

# Minimal software Convert scope; values are output stream kind/codec.
ENCODERS = {'aac': ('audio', 'aac'), 'pcm_s16le': ('audio', 'pcm_s16le'),
            'ffv1': ('video', 'ffv1'), 'libx264': ('video', 'h264'),
            'libx265': ('video', 'hevc'), 'mov_text': ('subtitle', 'mov_text'),
            'srt': ('subtitle', 'subrip'), 'ass': ('subtitle', 'ass')}


def fail(code: ValidationCode, message: str) -> None:
    raise PlanValidationError(code, message)


def validate_plan(plan: OperationPlan, available_encoders: frozenset[str] = frozenset()) -> None:
    """Pure validation; availability must come from the selected FFmpeg build."""
    if not isinstance(plan.operation, MediaOperation) or not isinstance(plan.output.container, Container):
        fail(ValidationCode.OPTION, 'Unsupported operation or container')
    if not plan.media.path.is_absolute() or not plan.output.path.is_absolute():
        fail(ValidationCode.OUTPUT, 'Operation paths must be absolute')
    if not plan.streams:
        fail(ValidationCode.STREAM, 'Select at least one stream')
    indices = [s.index for s in plan.streams]
    if any(type(i) is not int or i < 0 for i in indices) or len(set(indices)) != len(indices):
        fail(ValidationCode.STREAM, 'Invalid or duplicate stream selection')
    media_indices = [s.index for s in plan.media.streams]
    if len(set(media_indices)) != len(media_indices):
        fail(ValidationCode.STREAM, 'Ambiguous source stream indices')
    source = {s.index: s for s in plan.media.streams}
    for selection in plan.streams:
        if selection.index not in source:
            fail(ValidationCode.STREAM, f'Missing stream {selection.index}')
        stream, profile = source[selection.index], selection.profile
        codec = stream.codec
        if profile.encoder == 'copy':
            if any(v is not None for v in (profile.bitrate, profile.width, profile.height, profile.fps)):
                fail(ValidationCode.OPTION, 'Copy cannot specify encoding options or filters')
        else:
            if plan.operation == MediaOperation.REMUX:
                fail(ValidationCode.OPTION, 'Remux must copy every selected stream')
            if profile.encoder not in ENCODERS or profile.encoder not in available_encoders:
                fail(ValidationCode.OPTION, f'Encoder unavailable or unsupported: {profile.encoder}')
            kind, codec = ENCODERS[profile.encoder]
            if kind != stream.kind:
                fail(ValidationCode.OPTION, 'Encoder does not match stream type')
            if profile.bitrate is not None and (type(profile.bitrate) is not int or profile.bitrate <= 0 or profile.encoder not in {'aac', 'libx264', 'libx265'}):
                fail(ValidationCode.OPTION, 'Bitrate requires AAC, H.264 or H.265 and a positive integer value')
        if (profile.width is not None or profile.height is not None) and (stream.kind != 'video' or any(type(v) is not int or v <= 0 or v % 2 for v in (profile.width, profile.height))):
            fail(ValidationCode.OPTION, 'Resolution requires two positive even video dimensions')
        if profile.fps is not None:
            from fractions import Fraction
            if stream.kind != 'video' or not isinstance(profile.fps, Fraction) or not 0 < profile.fps <= 240:
                fail(ValidationCode.OPTION, 'Video FPS must be a positive rational value up to 240')
        if codec not in ALLOWED[plan.output.container].get(stream.kind, set()):
            fail(ValidationCode.COMPATIBILITY, f'Stream {stream.index}: {stream.kind}/{codec} is unsupported in {plan.output.container.value}')
    suffix = {Container.MATROSKA: '.mkv', Container.MP4: '.mp4'}[plan.output.container]
    if plan.output.path.suffix.lower() != suffix:
        fail(ValidationCode.OUTPUT, f'Destination must use {suffix}')
    for target in (plan.output.path, plan.output.temporary_path):
        if target is not None and (not target.is_absolute() or target == plan.media.path):
            fail(ValidationCode.OUTPUT, 'Source and output paths must be absolute and differ')
    temporary = plan.output.temporary_path
    if temporary is not None and (temporary == plan.output.path or temporary.parent != plan.output.path.parent):
        fail(ValidationCode.OUTPUT, 'Temporary output must be distinct and in the destination directory')

