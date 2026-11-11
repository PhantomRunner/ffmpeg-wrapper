"""Pure, typed FFmpeg command construction. Never creates shell strings."""
import os
from pathlib import Path

from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.operation_policy import validate_plan, video_pixel_format
from media_wrapper.domain.operations import OperationPlan, PreservationPolicy
from media_wrapper.domain.remux import Container, RemuxRequest


def build_remux_command(ffmpeg: Path, request: RemuxRequest) -> list[str]:
    if not isinstance(request.container, Container):
        raise TypeError('Unsupported container')
    if not request.streams or any(s.index < 0 for s in request.streams):
        raise ValueError('Select at least one valid stream')
    if len({s.index for s in request.streams}) != len(request.streams):
        raise ValueError('Duplicate stream selection')
    if request.source.resolve() == request.destination.resolve():
        raise ValueError('Source and destination must differ')
    args = [str(ffmpeg), '-hide_banner', '-nostdin', '-n', '-i', str(request.source.absolute())]
    for stream in request.streams:
        args.extend(['-map', f'0:{stream.index}'])
    args.extend(['-c', 'copy', '-f', CONTAINERS[request.container].muxer, str(request.destination.absolute())])
    return args


class CommandBuilder:
    """Deterministic argument generation; never probes or touches the filesystem."""

    def build(self, ffmpeg: Path, plan: 'OperationPlan',
              available_encoders: frozenset[str] = frozenset(), *, progress: bool = False) -> list[str]:
        validate_plan(plan, available_encoders)
        args = [str(ffmpeg), '-hide_banner', '-nostdin', '-n', '-i', str(plan.media.path)]
        if any(s.profile.encoder.endswith('_vaapi') for s in plan.streams):
            args[4:4] = ['-vaapi_device', plan.hardware_device]
        if progress:
            args[4:4] = ['-loglevel', 'error', '-progress', 'pipe:1', '-nostats']
        for selection in plan.streams:
            args.extend(['-map', f'0:{selection.index}'])
        source = {stream.index: stream for stream in plan.media.streams}
        if all(selection.profile.encoder == 'copy' for selection in plan.streams):
            args.extend(['-c', 'copy'])
        else:
            for position, selection in enumerate(plan.streams):
                profile, stream = selection.profile, source[selection.index]
                args.extend([f'-c:{position}', profile.encoder])
                if profile.encoder == 'copy':
                    continue
                pixel_format = video_pixel_format(stream, profile) if stream.kind == 'video' else None
                filters = [f'scale={profile.width}:{profile.height}'] if profile.width is not None else []
                if profile.encoder.endswith('_vaapi'):
                    filters.extend([f'format={pixel_format}', 'hwupload'])
                    pixel_format = None
                if filters:
                    args.extend([f'-filter:{position}', ','.join(filters)])
                codec_profile = profile.codec_profile
                if codec_profile is None and profile.encoder == 'dnxhd':
                    codec_profile = 'dnxhr_sq'
                bitrate = profile.bitrate
                if profile.crf is not None and profile.encoder in {'libaom-av1', 'libvpx-vp9'}:
                    bitrate = 0
                for flag, value in (
                    ('pix_fmt', pixel_format), ('crf', profile.crf), ('preset', profile.preset),
                    ('q', profile.audio_quality), ('r', profile.fps), ('b', bitrate),
                    ('profile', codec_profile), ('level', profile.level), ('ar', profile.sample_rate),
                    ('ac', profile.channels), ('channel_layout', profile.channel_layout),
                    ('colorspace', profile.color_space or (stream.color_space if stream.kind == 'video' else None)),
                    ('color_trc', profile.color_transfer or (stream.color_transfer if stream.kind == 'video' else None)),
                    ('color_primaries', profile.color_primaries or (stream.color_primaries if stream.kind == 'video' else None)),
                    ('color_range', profile.color_range or (stream.color_range if stream.kind == 'video' else None)),
                ):
                    if value is not None:
                        args.extend([f'-{flag}:{position}', str(value)])
        args.extend(['-map_metadata', '0' if plan.metadata_policy == PreservationPolicy.PRESERVE else '-1',
                     '-map_chapters', '0' if plan.chapter_policy == PreservationPolicy.PRESERVE else '-1'])
        for position, selection in enumerate(plan.streams):
            mapped = source[selection.index]
            keep_metadata = plan.metadata_policy == PreservationPolicy.PRESERVE
            args.extend([f'-map_metadata:s:{position}', f'0:s:{selection.index}' if keep_metadata else '-1'])
            if mapped.dispositions is not None:
                args.extend([f'-disposition:{position}', '+'.join(mapped.dispositions) or '0'])
            if mapped.title and keep_metadata and plan.output.container in {Container.MOV, Container.MP4, Container.M4A}:
                args.extend([f'-metadata:s:{position}', f'handler_name={mapped.title}'])
        for flag, value in plan.custom_options:
            args.extend([flag, value])
        args.extend(['-f', CONTAINERS[plan.output.container].muxer, str(plan.output.execution_path)])
        return args

    def build_passes(self, ffmpeg: Path, plan: OperationPlan, available_encoders: frozenset[str],
                     passlog: Path) -> list[list[str]]:
        command = self.build(ffmpeg, plan, available_encoders, progress=True)
        if not plan.two_pass:
            return [command]
        position = next(i for i, s in enumerate(plan.streams) if s.profile.encoder == 'libx264')
        first = command[:-3] + [f'-pass:{position}', '1', f'-passlogfile:{position}', str(passlog), '-f', 'null', os.devnull]
        second = command[:-3] + [f'-pass:{position}', '2', f'-passlogfile:{position}', str(passlog)] + command[-3:]
        return [first, second]
