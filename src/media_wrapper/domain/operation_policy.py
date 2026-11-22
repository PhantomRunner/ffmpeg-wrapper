"""Pure operation policy validation."""
import re
from fractions import Fraction

from media_wrapper.domain.capabilities import GPU_ENCODERS
from media_wrapper.domain.codec_policy import ALLOWED
from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.custom_options import validate_custom_options
from media_wrapper.domain.media import MediaStream
from media_wrapper.domain.operations import (
    EncodingProfile,
    MediaOperation,
    OperationPlan,
    PlanValidationError,
    PreservationPolicy,
    ValidationCode,
)
from media_wrapper.domain.remux import Container

# The encoder registry is also used by presets, import and output verification.
ENCODERS = {
    'aac': ('audio', 'aac'), 'pcm_s16le': ('audio', 'pcm_s16le'),
    'pcm_s24le': ('audio', 'pcm_s24le'), 'pcm_s32le': ('audio', 'pcm_s32le'),
    'pcm_f32le': ('audio', 'pcm_f32le'), 'flac': ('audio', 'flac'),
    'alac': ('audio', 'alac'), 'libopus': ('audio', 'opus'), 'libmp3lame': ('audio', 'mp3'),
    'ffv1': ('video', 'ffv1'), 'libx264': ('video', 'h264'), 'libx265': ('video', 'hevc'),
    'libsvtav1': ('video', 'av1'), 'libaom-av1': ('video', 'av1'), 'libvpx-vp9': ('video', 'vp9'),
    'dnxhd': ('video', 'dnxhd'), 'prores_ks': ('video', 'prores'),
    'mov_text': ('subtitle', 'mov_text'), 'srt': ('subtitle', 'subrip'),
    'ass': ('subtitle', 'ass'), 'webvtt': ('subtitle', 'webvtt'),
    **{name: ('video', codec) for name, codec in GPU_ENCODERS.items()},
}
QUALITY_MAX = {'libx264': 51, 'libx265': 51, 'libsvtav1': 63, 'libaom-av1': 63, 'libvpx-vp9': 63}
BITRATE_ENCODERS = frozenset({'aac', 'libopus', 'libmp3lame', *QUALITY_MAX, *GPU_ENCODERS})
SPEED_PRESET_ENCODERS = frozenset({'libx264', 'libx265'})
CODEC_PROFILES = {
    'dnxhd': frozenset({'dnxhr_lb', 'dnxhr_sq', 'dnxhr_hq', 'dnxhr_hqx', 'dnxhr_444'}),
    'prores_ks': frozenset({'proxy', 'lt', 'standard', 'hq', '4444', '4444xq'}),
    'libx264': frozenset({'baseline', 'main', 'high', 'high10', 'high422', 'high444'}),
    'libx265': frozenset({'main', 'main10', 'mainstillpicture'}),
}
COLOR_FIELDS = ('color_space', 'color_transfer', 'color_primaries', 'color_range')
_SDR_COLOR_VALUES = (
    ('space', {'bt709', 'fcc', 'bt470bg', 'smpte170m', 'smpte240m', 'ycgco', 'gbr', 'bt2020nc'}),
    ('trc', {'bt709', 'gamma22', 'gamma28', 'smpte170m', 'smpte240m', 'linear', 'iec61966-2-1', 'bt2020-10', 'bt2020-12'}),
    ('primaries', {'bt709', 'bt470m', 'bt470bg', 'smpte170m', 'smpte240m', 'film', 'bt2020', 'smpte431', 'smpte432'}),
    ('range', {'tv', 'pc'}),
)


def video_pixel_format(stream: MediaStream, profile: EncodingProfile) -> str | None:
    if profile.pixel_format:
        return profile.pixel_format
    high_depth = (stream.bit_depth or 8) > 8
    if profile.encoder == 'dnxhd':
        if profile.codec_profile == 'dnxhr_444':
            return 'yuv444p10le'
        return 'yuv422p10le' if profile.codec_profile == 'dnxhr_hqx' else 'yuv422p'
    if profile.encoder == 'prores_ks':
        return 'yuv444p10le' if profile.codec_profile in {'4444', '4444xq'} else 'yuv422p10le'
    if profile.encoder in GPU_ENCODERS:
        return 'p010le' if high_depth else 'nv12'
    if profile.encoder in {'libx264', 'libx265'} and not stream.pixel_format:
        return 'yuv420p'
    if profile.encoder in QUALITY_MAX or profile.encoder == 'ffv1':
        return stream.pixel_format
    return None


def color_conversion_filter(stream: MediaStream, profile: EncodingProfile) -> str | None:
    if not any(
        (value := getattr(profile, field)) is not None and value != getattr(stream, field)
        for field in COLOR_FIELDS
    ):
        return None
    pairs = []
    for field, (flag, supported) in zip(COLOR_FIELDS, _SDR_COLOR_VALUES, strict=True):
        input_value = getattr(stream, field)
        output_value = getattr(profile, field) or input_value
        if input_value not in supported or output_value not in supported:
            fail(ValidationCode.OPTION, 'Color conversion needs known, supported SDR color metadata. HDR tone mapping is unavailable.')
        pairs.append(f'{flag}={output_value}')
    return 'colorspace=' + ':'.join(pairs)


def _valid_token(value: str) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_.()+-]{1,48}', value)) and not value.startswith('-')


def _validate_profile(stream: MediaStream, profile: EncodingProfile) -> None:
    if profile.encoder == 'copy':
        if profile != EncodingProfile():
            fail(ValidationCode.OPTION, 'Copy cannot specify encoding options or filters')
        return
    if profile.bitrate is not None and (
        type(profile.bitrate) is not int or profile.bitrate <= 0 or profile.encoder not in BITRATE_ENCODERS
    ):
        fail(ValidationCode.OPTION, 'This encoder requires a supported positive bitrate or its default rate control')
    if (profile.width is not None or profile.height is not None) and (
        stream.kind != 'video' or any(type(v) is not int or v <= 0 or v % 2 for v in (profile.width, profile.height))
    ):
        fail(ValidationCode.OPTION, 'Resolution requires two positive even video dimensions')
    if profile.fps is not None and (
        stream.kind != 'video' or not isinstance(profile.fps, Fraction) or not 0 < profile.fps <= 240
    ):
        fail(ValidationCode.OPTION, 'Video FPS must be a positive rational value up to 240')
    if profile.crf is not None and (
        type(profile.crf) is not int or not 0 <= profile.crf <= QUALITY_MAX.get(profile.encoder, -1)
        or profile.bitrate is not None
    ):
        fail(ValidationCode.OPTION, 'Unsupported constant quality value or a conflicting bitrate')
    if profile.preset is not None and (
        profile.encoder not in SPEED_PRESET_ENCODERS
        or profile.preset not in {'ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'}
    ):
        fail(ValidationCode.OPTION, 'Unsupported encoder speed preset')
    audio_quality = {'aac': range(1, 6), 'libmp3lame': range(10)}
    if profile.audio_quality is not None and (
        type(profile.audio_quality) is not int or profile.audio_quality not in audio_quality.get(profile.encoder, ())
        or profile.bitrate is not None
    ):
        fail(ValidationCode.OPTION, 'Unsupported audio quality or a conflicting bitrate')
    if profile.sample_rate is not None and (
        stream.kind != 'audio' or type(profile.sample_rate) is not int or not 8_000 <= profile.sample_rate <= 384_000
    ):
        fail(ValidationCode.OPTION, 'Audio sample rate must be between 8,000 and 384,000 Hz')
    if profile.channels is not None and (
        stream.kind != 'audio' or type(profile.channels) is not int or not 1 <= profile.channels <= 8
    ):
        fail(ValidationCode.OPTION, 'Audio channel count must be between one and eight')
    if profile.channel_layout is not None and (stream.kind != 'audio' or not _valid_token(profile.channel_layout)):
        fail(ValidationCode.OPTION, 'Invalid channel layout')
    if profile.codec_profile is not None and profile.codec_profile not in CODEC_PROFILES.get(profile.encoder, ()):
        fail(ValidationCode.OPTION, 'Unsupported codec profile for this encoder')
    if profile.level is not None and (profile.encoder not in SPEED_PRESET_ENCODERS or not _valid_token(profile.level)):
        fail(ValidationCode.OPTION, 'Codec level requires H.264 or H.265 and a supported level name')
    if any(
        value is not None and (stream.kind != 'video' or not _valid_token(value))
        for value in (profile.pixel_format, *(getattr(profile, field) for field in COLOR_FIELDS))
    ):
        fail(ValidationCode.OPTION, 'Invalid video pixel format or color setting')
    if stream.kind == 'video':
        color_conversion_filter(stream, profile)
    if (stream.bit_depth or 8) > 8 and profile.encoder == 'dnxhd' and profile.pixel_format is None and video_pixel_format(stream, profile) == 'yuv422p':
        fail(ValidationCode.OPTION, 'This DNxHR profile uses 8-bit video. Use HQX or explicitly choose 8-bit video.')
    if (stream.bit_depth or 8) > 12 and profile.encoder in {'dnxhd', 'prores_ks', *GPU_ENCODERS} and profile.pixel_format is None:
        fail(ValidationCode.OPTION, 'This encoder may reduce source bit depth. Explicitly select a supported pixel format.')


def fail(code: ValidationCode, message: str) -> None:
    raise PlanValidationError(code, message)


def validate_plan(plan: OperationPlan, available_encoders: frozenset[str] = frozenset()) -> None:
    """Pure validation; availability must come from the selected FFmpeg build."""
    try:
        validate_custom_options(plan.custom_options)
    except ValueError as error:
        fail(ValidationCode.OPTION, str(error))
    if type(plan.deep_verify) is not bool or type(plan.cpu_fallback) is not bool:
        fail(ValidationCode.OPTION, 'Invalid verification or hardware fallback policy')
    if not isinstance(plan.metadata_policy, PreservationPolicy) or not isinstance(plan.chapter_policy, PreservationPolicy):
        fail(ValidationCode.OPTION, 'Unsupported metadata/chapter policy')
    if not isinstance(plan.operation, MediaOperation) or not isinstance(plan.output.container, Container):
        fail(ValidationCode.OPTION, 'Unsupported operation or container')
    if not plan.media.path.is_absolute() or not plan.output.path.is_absolute():
        fail(ValidationCode.OUTPUT, 'Operation paths must be absolute')
    if not plan.streams:
        fail(ValidationCode.STREAM, 'Select at least one stream')
    spec = CONTAINERS[plan.output.container]
    if spec.max_streams is not None and len(plan.streams) > spec.max_streams:
        fail(ValidationCode.COMPATIBILITY, f'{spec.label} supports at most {spec.max_streams} selected stream')
    if not spec.chapters and plan.media.chapters and plan.chapter_policy == PreservationPolicy.PRESERVE:
        fail(ValidationCode.COMPATIBILITY, f'{spec.label} cannot preserve chapters; choose Strip chapters')
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
        if stream.is_artwork and not spec.artwork:
            fail(ValidationCode.COMPATIBILITY, f'Stream {stream.index}: {spec.label} cannot preserve artwork without changing its role')
        if profile.encoder != 'copy':
            if plan.operation == MediaOperation.REMUX:
                fail(ValidationCode.OPTION, 'Remux must copy every selected stream')
            if profile.encoder not in ENCODERS or profile.encoder not in available_encoders:
                fail(ValidationCode.OPTION, f'Encoder unavailable or unsupported: {profile.encoder}')
            if stream.kind == 'subtitle' and stream.codec not in {'subrip', 'ass', 'ssa', 'webvtt', 'mov_text', 'text'}:
                fail(ValidationCode.OPTION, 'Bitmap subtitle conversion is unsupported; copy to a compatible container or omit')
            kind, codec = ENCODERS[profile.encoder]
            if kind != stream.kind or stream.is_artwork:
                fail(ValidationCode.OPTION, 'Encoder does not match stream type')
        _validate_profile(stream, profile)
        if profile.encoder.endswith('_vaapi') and not plan.hardware_device:
            fail(ValidationCode.OPTION, 'VAAPI requires an explicit tested render device')
        if codec not in ALLOWED[plan.output.container].get(stream.kind, set()):
            fail(ValidationCode.COMPATIBILITY, f'Stream {stream.index}: {stream.kind}/{codec} is unsupported in {plan.output.container.value}')
    if spec.audio_only:
        streams = [source[s.index] for s in plan.streams]
        if sum(stream.kind == 'audio' for stream in streams) != 1 or any(
            stream.kind != 'audio' and not stream.is_artwork for stream in streams
        ):
            fail(ValidationCode.COMPATIBILITY, f'{spec.label} supports at most one audio stream and only compatible cover artwork')
    if plan.two_pass:
        video = [s for s in plan.streams if source[s.index].kind == 'video']
        if len(video) != 1 or video[0].profile.encoder != 'libx264' or video[0].profile.bitrate is None or video[0].profile.crf is not None:
            fail(ValidationCode.OPTION, 'Two-pass encoding requires one bitrate-controlled libx264 video')
    suffix = CONTAINERS[plan.output.container].extension
    if plan.output.path.suffix.lower() != suffix:
        fail(ValidationCode.OUTPUT, f'Destination must use {suffix}')
    for target in (plan.output.path, plan.output.temporary_path):
        if target is not None and (not target.is_absolute() or target == plan.media.path):
            fail(ValidationCode.OUTPUT, 'Source and output paths must be absolute and differ')
    temporary = plan.output.temporary_path
    if temporary is not None and (temporary == plan.output.path or temporary.parent != plan.output.path.parent):
        fail(ValidationCode.OUTPUT, 'Temporary output must be distinct and in the destination directory')

