"""Pure, typed FFmpeg command construction. Never creates shell strings."""
from pathlib import Path

from media_wrapper.domain.operation_policy import validate_plan
from media_wrapper.domain.operations import OperationPlan
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
                if profile.width is not None:
                    args.extend([f'-filter:{position}', f'scale={profile.width}:{profile.height}'])
                if profile.fps is not None:
                    args.extend([f'-r:{position}', str(profile.fps)])
                if selection.profile.bitrate is not None:
                    args.extend([f'-b:{position}', str(selection.profile.bitrate)])
        args.extend(['-f', plan.output.container.value, str(plan.output.execution_path)])
        return args
