"""Prepare typed plans in a worker before handing arguments to a process runner."""
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from media_wrapper.application.operation_validation import validate_paths, validate_plan
from media_wrapper.domain.containers import CONTAINERS
from media_wrapper.domain.operation_policy import COLOR_FIELDS, video_pixel_format
from media_wrapper.domain.operations import OperationPlan, PreservationPolicy
from media_wrapper.domain.remux import Container
from media_wrapper.domain.target_size import apply_target_size
from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder


def prepare_operation(plan: OperationPlan, *, staged: bool = True,
                      available_encoders: frozenset[str] = frozenset()) -> OperationPlan:
    """No files are created. OperationTask verifies and publishes staged output.

    Revalidate immediately before starting; -n protects the execution target.
    A caller must publish staged output without replacing an existing final file.
    """
    plan = apply_target_size(plan)
    validate_plan(plan, available_encoders)
    validate_paths(plan)
    if staged and plan.output.temporary_path is None:
        output = plan.output
        temporary = output.path.with_name(f'.{uuid4().hex}.partial{output.path.suffix}')
        plan = replace(plan, output=replace(output, temporary_path=temporary))
    validate_plan(plan, available_encoders)
    validate_paths(plan)
    return plan


def prepare_command(ffmpeg: Path, plan: OperationPlan, *, staged: bool = True,
                    available_encoders: frozenset[str] = frozenset()) -> tuple[OperationPlan, list[str]]:
    prepared = prepare_operation(plan, staged=staged, available_encoders=available_encoders)
    if prepared.two_pass:
        raise ValueError('Two-pass plans require CommandBuilder.build_passes and sequential execution')
    return prepared, CommandBuilder().build(ffmpeg, prepared, available_encoders)



def operation_warnings(plan: OperationPlan) -> tuple[str, ...]:
    """Report known format changes and planning assumptions before execution."""
    warnings = []
    if plan.hardware_note:
        warnings.append(plan.hardware_note)
    if plan.target_size_bytes is not None:
        warnings.append(f'Strict maximum: {plan.target_size_bytes:,} bytes. Only video bitrate may be reduced on retry.')
    source = {stream.index: stream for stream in plan.media.streams}
    container = CONTAINERS[plan.output.container]
    for selected in plan.streams:
        stream, profile = source[selected.index], selected.profile
        prefix = f'Stream {stream.index}'
        if profile.encoder != 'copy' and stream.kind == 'video':
            pixel_format = video_pixel_format(stream, profile)
            if stream.pixel_format and pixel_format and stream.pixel_format != pixel_format:
                warnings.append(f'{prefix} pixel format: {stream.pixel_format} → {pixel_format}.')
            if any(
                any(flag in item.lower() for flag in ('hdr', 'mastering display', 'dolby vision', 'content light'))
                for item in stream.side_data
            ):
                warnings.append(f'{prefix} has HDR metadata that may be lost when encoded. Use Copy if it must be preserved.')
            if any(getattr(profile, field) is not None and getattr(profile, field) != getattr(stream, field) for field in COLOR_FIELDS):
                warnings.append(f'{prefix} color tags are explicitly changed. This does not apply a color or tone mapping transform.')
        if profile.sample_rate is not None and profile.sample_rate != stream.sample_rate:
            warnings.append(f'{prefix} is resampled to {profile.sample_rate:,} Hz.')
        if plan.metadata_policy == PreservationPolicy.PRESERVE and (stream.title or stream.language) and plan.output.container not in {
            Container.MATROSKA, Container.MOV, Container.MP4, Container.M4A,
        }:
            warnings.append(f'{prefix} title or language may be lost in {container.label}.')
    return tuple(warnings)
