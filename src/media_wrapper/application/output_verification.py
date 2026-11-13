"""Check output contracts against the actual FFprobe metadata and filesystem."""

from media_wrapper.domain.media import MediaFile, MediaStream
from media_wrapper.domain.operation_policy import COLOR_FIELDS, ENCODERS
from media_wrapper.domain.operations import (
    EncodingProfile,
    OperationPlan,
    PreservationPolicy,
)
from media_wrapper.domain.remux import Container


def verify_output(plan: OperationPlan, info: MediaFile) -> None:
    sources = {stream.index: stream for stream in plan.media.streams}
    expected = tuple((sources[s.index], s.profile) for s in plan.streams)
    actual = info.streams
    if _generated_chapter_track(plan, info, len(expected)):
        actual = actual[:-1]
    if not info.size_bytes or len(actual) != len(expected):
        raise ValueError('Output verification failed: selected stream count or size differs')
    for (source, profile), stream in zip(expected, actual, strict=True):
        _verify_stream(plan, source, profile, stream)
    _verify_duration(plan, expected, info)
    if plan.chapter_policy == PreservationPolicy.STRIP and info.chapters:
        raise ValueError('Output chapter removal verification failed')
    if plan.chapter_policy == PreservationPolicy.PRESERVE and len(info.chapters) != len(plan.media.chapters):
        raise ValueError('Output chapter count verification failed')


def _generated_chapter_track(plan: OperationPlan, info: MediaFile, expected_count: int) -> bool:
    if (
        plan.output.container not in {Container.MP4, Container.MOV}
        or plan.chapter_policy != PreservationPolicy.PRESERVE
        or not plan.media.chapters or not info.chapters or len(info.streams) != expected_count + 1
    ):
        return False
    stream = info.streams[-1]
    return (stream.kind, stream.codec, stream.codec_tag) == ('data', 'bin_data', 'text')


def _verify_stream(plan: OperationPlan, source: MediaStream, profile: EncodingProfile, actual: MediaStream) -> None:
    codec = source.codec if profile.encoder == 'copy' else ENCODERS[profile.encoder][1]
    if (actual.kind, actual.codec) != (source.kind, codec):
        raise ValueError(f'Output stream {actual.index} verification failed: expected {source.kind}/{codec}')
    if source.is_artwork != actual.is_artwork:
        raise ValueError('Output cover artwork verification failed')
    if source.kind == 'video' and not source.is_artwork:
        _verify_video(source, profile, actual)
    if source.kind == 'audio':
        _verify_audio(source, profile, actual)
    if plan.metadata_policy == PreservationPolicy.STRIP:
        return
    if plan.output.container in {Container.MATROSKA, Container.MP4, Container.MOV}:
        if source.title and actual.title != source.title:
            raise ValueError(f'Output stream {actual.index} title verification failed')
        if source.language and len(source.language) == 3 and (actual.language or 'und') != source.language:
            raise ValueError(f'Output stream {actual.index} language verification failed')
    if plan.output.container == Container.MATROSKA and source.dispositions is not None:
        # Compare persistent flags known to the Matroska muxer.
        known = {'default', 'forced', 'hearing_impaired', 'visual_impaired', 'original', 'comment'}
        if set(source.dispositions) & known != set(actual.dispositions or ()) & known:
            raise ValueError(f'Output stream {actual.index} disposition verification failed')


def _verify_video(source: MediaStream, profile: EncodingProfile, actual: MediaStream) -> None:
    resolution = (profile.width, profile.height) if profile.width is not None else (source.width, source.height)
    if None not in resolution and (actual.width, actual.height) != resolution:
        raise ValueError('Output resolution verification failed')
    fps = profile.fps or source.frame_rate
    if fps is not None and actual.frame_rate is not None:
        delta = abs(actual.frame_rate - fps)
        if delta > max(0.1, float(fps) * 0.015):
            raise ValueError('Output frame rate verification failed')
    if profile.pixel_format and not profile.encoder.endswith('_vaapi') and actual.pixel_format != profile.pixel_format:
        raise ValueError('Output pixel format verification failed')
    if not profile.pixel_format and (source.bit_depth or 0) > (actual.bit_depth or source.bit_depth or 0):
        raise ValueError('Output bit depth verification failed')
    for field in COLOR_FIELDS:
        expected = getattr(profile, field) or getattr(source, field)
        observed = getattr(actual, field)
        if (
            field == 'color_range' and profile.color_range is None and expected == 'tv' and observed is None
            and (source.pixel_format or '').startswith('yuv') and source.pixel_format == actual.pixel_format
        ):
            # Some muxers omit limited-range tagging for ordinary YUV.
            observed = 'tv'
        if expected and observed != expected:
            raise ValueError(f'Output {field.replace("_", " ")} verification failed')


def _verify_audio(source: MediaStream, profile: EncodingProfile, actual: MediaStream) -> None:
    rate = profile.sample_rate or source.sample_rate
    if rate is not None and rate != actual.sample_rate:
        raise ValueError('Output sample rate verification failed')
    channels = profile.channels or (None if profile.channel_layout else source.channels)
    if channels is not None and channels != actual.channels:
        raise ValueError('Output channel count verification failed')
    layout = profile.channel_layout or (None if profile.channels else source.channel_layout)
    if layout is not None and layout != actual.channel_layout:
        raise ValueError('Output channel layout verification failed')


def _verify_duration(plan: OperationPlan, expected: tuple[tuple[MediaStream, EncodingProfile], ...], info: MediaFile) -> None:
    selected_av = [stream for stream, _ in expected if stream.kind in {'audio', 'video'} and not stream.is_artwork]
    if not selected_av:
        return
    source_av = [stream for stream in plan.media.streams if stream.kind in {'audio', 'video'} and not stream.is_artwork]
    duration = (
        plan.media.duration if len(source_av) == len(selected_av)
        else max((stream.duration for stream in selected_av if stream.duration is not None), default=None)
    )
    if duration is None:
        return
    frame_intervals = [1 / stream.frame_rate for stream in selected_av if stream.frame_rate]
    tolerance = max(0.25, 2 * max(frame_intervals, default=0))
    if info.duration is None or abs(info.duration - duration) > tolerance:
        raise ValueError(f'Output duration verification failed: expected {duration:.2f}s, actual {info.duration}s')
