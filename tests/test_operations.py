from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import (
    EncodingProfile,
    MediaOperation,
    OperationPlan,
    OutputTarget,
    PlanValidationError,
    StreamSelection,
    ValidationCode,
)
from media_wrapper.domain.remux import Container


def test_immutable_plan_and_safe_defaults():
    plan = OperationPlan(MediaOperation.REMUX, MediaFile(Path('input')),
                         (StreamSelection(3),), OutputTarget(Path('out.mkv'), Container.MATROSKA))
    assert plan.streams[0].profile == EncodingProfile('copy', None)
    assert plan.output.execution_path == Path('out.mkv')
    with pytest.raises(FrozenInstanceError):
        plan.operation = MediaOperation.CONVERT
    error = PlanValidationError(ValidationCode.STREAM, 'Missing stream')
    assert error.code == ValidationCode.STREAM and str(error) == 'Missing stream'
