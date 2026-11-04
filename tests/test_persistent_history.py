import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from test_flat_workbench import flat_window, wait  # noqa: F401 - fixture shared with workbench tests

from media_wrapper.domain.history_document import record_payload
from media_wrapper.domain.tasks import TaskRecord, TaskStatus
from media_wrapper.infrastructure.history_repository import HistoryRepository
from media_wrapper.ui.history_sync import HistorySync


def terminal(plan):
    record = TaskRecord(plan)
    record.transition(TaskStatus.PREPARING)
    record.transition(TaskStatus.RUNNING)
    record.log = 'bounded FFmpeg log'
    record.command = ('ffmpeg', '-n', '-i', str(plan.media.path))
    record.transition(TaskStatus.FAILED)
    return record


def test_history_roundtrip_needs_no_sources_and_preserves_media_files(sample, tmp_path):
    _, plan = sample
    record = terminal(plan)
    marker = tmp_path / 'user-output.mkv'
    marker.write_bytes(b'keep')
    repository = HistoryRepository(tmp_path / 'data/history.json')
    repository.merge((record_payload(record),))
    record.plan.media.path.unlink()
    loaded = repository.read()
    assert len(loaded) == 1 and loaded[0].plan == record.plan
    assert loaded[0].command == record.command and loaded[0].log == record.log
    repository.merge(remove=(record.id,))
    assert repository.read() == () and marker.read_bytes() == b'keep'


def test_concurrent_merge_and_captured_clear_scope(sample, tmp_path):
    _, plan = sample
    a, b = terminal(plan), terminal(replace(plan, output=replace(plan.output, path=tmp_path / 'other.mkv')))
    path = tmp_path / 'history.json'
    with ThreadPoolExecutor(2) as executor:
        futures = [executor.submit(HistoryRepository(path).merge, (record_payload(record),)) for record in (a, b)]
        for future in futures:
            future.result()
    repository = HistoryRepository(path)
    assert {r.id for r in repository.read()} == {a.id, b.id}
    repository.merge(remove=(a.id,))
    assert [r.id for r in repository.read()] == [b.id]


@pytest.mark.parametrize('content', ['{bad', '{"kind":"media-wrapper-history","version":99,"records":[]}',
                                    '{"kind":"media-wrapper-history","version":1,"version":1,"records":[]}'])
def test_unknown_or_corrupt_history_is_never_replaced(sample, tmp_path, content):
    path = tmp_path / 'history.json'
    path.write_text(content)
    repository = HistoryRepository(path)
    with pytest.raises(ValueError):
        repository.merge((record_payload(terminal(sample[1])),))
    assert path.read_text() == content
    assert not path.with_name('history.json.lock').exists()


def test_async_terminal_history_and_clear_do_not_delete_source(flat_window, sample, tmp_path):  # noqa: F811 - imported pytest fixture
    app, window = flat_window
    repository = HistoryRepository(tmp_path / 'history.json')
    window.history_sync = HistorySync(window.controller, repository)
    window.controller.import_sources((sample[1].media.path,))
    wait(app, lambda: not window.controller.busy)
    window.controller.prepare('enqueue')
    wait(app, lambda: not window.controller.busy)
    record = window.controller.queue.records[0]
    assert record.status == TaskStatus.PENDING
    window.controller.queue.cancel(record.id)
    wait(app, lambda: not window.controller.busy)
    assert repository.read()[0].status == TaskStatus.CANCELLED
    assert json.loads(repository.path.read_text())['version'] == 1
    window.clear_history((record.id,))
    wait(app, lambda: not window.controller.busy)
    assert not window.controller.queue.records and repository.read() == ()
    assert sample[1].media.path.exists()
