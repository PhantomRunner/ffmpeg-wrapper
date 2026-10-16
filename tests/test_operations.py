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


@pytest.fixture
def plan(tmp_path):
    from media_wrapper.domain.media import MediaStream
    source = tmp_path/'source ü.wav'
    source.write_bytes(b'source')
    return OperationPlan(MediaOperation.REMUX, MediaFile(source, streams=(MediaStream(2, 'audio', 'aac'),)),
                         (StreamSelection(2),), OutputTarget(tmp_path/'out.mp4', Container.MP4))


def test_validation_and_existing_output(plan):
    from media_wrapper.application.operation_validation import (
        validate_paths,
        validate_plan,
    )
    validate_plan(plan)
    validate_paths(plan)
    plan.output.path.write_bytes(b'keep')
    with pytest.raises(PlanValidationError) as error:
        validate_paths(plan)
    assert error.value.code == ValidationCode.OUTPUT
    assert plan.output.path.read_bytes() == b'keep'


@pytest.mark.parametrize('streams,code', [
    ((), ValidationCode.STREAM),
    ((StreamSelection(4),), ValidationCode.STREAM),
    ((StreamSelection(2), StreamSelection(2)), ValidationCode.STREAM),
    ((StreamSelection(2, EncodingProfile('copy', 128000)),), ValidationCode.OPTION),
    ((StreamSelection(2, EncodingProfile('aac')),), ValidationCode.OPTION),
])
def test_invalid_selection_and_options(plan, streams, code):
    from dataclasses import replace

    from media_wrapper.application.operation_validation import validate_plan
    with pytest.raises(PlanValidationError) as error:
        validate_plan(replace(plan, streams=streams), frozenset({'aac'}))
    assert error.value.code == code
