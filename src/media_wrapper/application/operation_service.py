"""Prepare typed plans in a worker before handing arguments to a process runner."""
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from media_wrapper.application.operation_validation import validate_paths, validate_plan
from media_wrapper.domain.operations import OperationPlan
from media_wrapper.domain.target_size import apply_target_size
from media_wrapper.infrastructure.ffmpeg.command_builder import CommandBuilder


def prepare_operation(plan: OperationPlan, *, staged: bool = True,
                      available_encoders: frozenset[str] = frozenset()) -> OperationPlan:
    """No files are created. Finalization belongs to the future common runner.

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
    return prepared, CommandBuilder().build(ffmpeg, prepared, available_encoders)
