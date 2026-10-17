"""Pure, typed FFmpeg command construction. Never creates shell strings."""
import os
from pathlib import Path

from media_wrapper.domain.capabilities import GPU_ENCODERS
from media_wrapper.domain.operation_policy import validate_plan
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
    args.extend(['-c', 'copy', '-f', request.container.value, str(request.destination.absolute())])
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
            args[4:4] = ['-progress', 'pipe:1', '-nostats']
        for selection in plan.streams:
            args.extend(['-map', f'0:{selection.index}'])
        if all(selection.profile.encoder == 'copy' for selection in plan.streams):
            args.extend(['-c', 'copy'])
        else:
            for position, selection in enumerate(plan.streams):
                args.extend([f'-c:{position}', selection.profile.encoder])
                profile = selection.profile
                if profile.encoder in {'libx264', 'libx265'}:
                    args.extend([f'-pix_fmt:{position}', 'yuv420p'])
                if profile.crf is not None:
                    args.extend([f'-crf:{position}', str(profile.crf)])
                if profile.preset is not None:
                    args.extend([f'-preset:{position}', profile.preset])
                if profile.audio_quality is not None:
                    args.extend([f'-q:{position}', str(profile.audio_quality)])
                filters = [f'scale={profile.width}:{profile.height}'] if profile.width is not None else []
                if profile.encoder.endswith('_vaapi'):
                    filters.extend(['format=nv12', 'hwupload'])
                elif profile.encoder in GPU_ENCODERS:
                    args.extend([f'-pix_fmt:{position}', 'nv12'])
                if filters:
                    args.extend([f'-filter:{position}', ','.join(filters)])
                if profile.fps is not None:
                    args.extend([f'-r:{position}', str(profile.fps)])
                if selection.profile.bitrate is not None:
                    args.extend([f'-b:{position}', str(selection.profile.bitrate)])
        args.extend(['-map_metadata', '0' if plan.metadata_policy == PreservationPolicy.PRESERVE else '-1',
                     '-map_chapters', '0' if plan.chapter_policy == PreservationPolicy.PRESERVE else '-1'])
        for position, selection in enumerate(plan.streams):
            args.extend([f'-map_metadata:s:{position}', f'0:s:{selection.index}' if plan.metadata_policy == PreservationPolicy.PRESERVE else '-1'])
        for flag, value in plan.custom_options:
            args.extend([flag, value])
        args.extend(['-f', plan.output.container.value, str(plan.output.execution_path)])
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
