from pathlib import Path

import pytest

from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import (
    MediaOperation,
    OperationPlan,
    OutputTarget,
    StreamSelection,
)
from media_wrapper.domain.remux import Container
from media_wrapper.domain.tasks import TRANSITIONS, TaskRecord, TaskStatus


def record():
    return TaskRecord(OperationPlan(MediaOperation.REMUX, MediaFile(Path('input')),
                                   (StreamSelection(0),), OutputTarget(Path('out.mkv'), Container.MATROSKA)))


@pytest.mark.parametrize('before', list(TaskStatus))
@pytest.mark.parametrize('after', list(TaskStatus))
def test_transition_table(before, after):
    task = record()
    task.status = before
    if after in TRANSITIONS[before]:
        task.transition(after)
        assert task.status == after
    else:
        with pytest.raises(ValueError):
            task.transition(after)
        assert task.status == before


def test_task_identity_and_bounded_log():
    first, second = record(), record()
    assert first.id != second.id
    first.append_log('x' * 20000)
    assert len(first.log) == 16000 and not second.log
