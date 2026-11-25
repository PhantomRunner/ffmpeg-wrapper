"""Desktop acceptance coverage for independent processing outputs."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QInputDialog
from test_flat_workbench import flat_window, wait  # noqa: F401 - shared pytest fixture

from media_wrapper.domain.draft import EditScope
from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.ui.source_tree import SourceTreeModel


def test_output_rows_queue_independently(flat_window, sample):  # noqa: F811
    app, window = flat_window
    controller, draft = window.controller, window.draft
    source_path = sample[1].media.path
    controller.import_sources((source_path,))
    wait(app, lambda: not controller.busy)
    window.render()
    source = next(iter(draft.items.values()))
    first = draft.outputs_for(source.id)[0]
    window.add_version.click()
    first, second = draft.outputs_for(source.id)
    assert first.id != second.id and draft.active_output_id == second.id
    assert draft.scope is EditScope.ACTIVE

    tree = window.sources.model
    parent = tree.index_for_id(source.id)
    second_row = tree.index_for_id(second.id)
    assert tree.parent(second_row).data(SourceTreeModel.ID_ROLE) == source.id
    assert tree.data(parent, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
    window.sources.select_id(first.id)
    proxy_row = window.sources.proxy.mapFromSource(second_row)
    view = window.sources.table
    rect = view.visualRect(proxy_row)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.left() + 20, rect.center().y()))
    assert tree.data(parent, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.PartiallyChecked
    assert draft.active_output_id == first.id and window.sources.row_ids() == (first.id,)
    tree.setData(parent, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert first.included and second.included

    window.sources.select_id(second.id)
    controller.patch('template', '{name}_second')
    before = first.options[first.operation].template
    assert before != second.options[second.operation].template
    window.sources.select_id(first.id)
    assert draft.active_output_id == first.id and draft.scope is EditScope.ACTIVE
    assert first.options[first.operation].template == before
    controller.prepare('start')
    wait(app, lambda: not controller.busy and not controller.queue.running and len(controller.queue.records) == 2)
    records = controller.queue.records
    assert all(job.status == TaskStatus.COMPLETED for job in records), [(job.status, job.error) for job in records]
    assert len({job.plan.output.path for job in records}) == 2
    assert source_path.is_file() and all(job.result.path.is_file() for job in records)


def test_inspector_focus_filter_and_keyboard_inclusion(flat_window, sample, tmp_path):  # noqa: F811
    app, window = flat_window
    original = sample[1].media.path
    copy = tmp_path / 'different.wav'
    copy.write_bytes(original.read_bytes())
    window.controller.import_sources((original, copy))
    wait(app, lambda: not window.controller.busy)
    window.render()
    draft = window.draft
    by_path = {item.path: item.id for item in draft.items.values()}
    source_id = by_path[original]
    detail_id = by_path[copy]
    output = draft.outputs_for(source_id)[0]
    window.inspect_source(detail_id)
    metadata = window._dialogs[-1]
    assert metadata.windowTitle() == f'Inspect source · {copy.name}'
    metadata.close()
    window.sources.select_id(output.id)
    assert draft.inspector_source_id == detail_id and draft.active_output_id == output.id

    window.sources.search.setText('different')
    assert window.sources.proxy.rowCount() == 1
    window.sources.search.clear()
    assert window.sources.proxy.rowCount() == 2
    assert window.sources.row_ids() == (output.id,)
    view = window.sources.table
    view.setFocus()
    QTest.keyClick(view, Qt.Key.Key_Space)
    assert not output.included
    assert draft.inspector_source_id == detail_id and draft.active_output_id == output.id


def test_theme_and_results_routes(flat_window):  # noqa: F811
    app, window = flat_window
    window.theme_picker.setCurrentIndex(window.theme_picker.findData('dark'))
    dark = window.styleSheet()
    assert window.preferences().theme == 'dark'
    window.theme_picker.setCurrentIndex(window.theme_picker.findData('light'))
    assert window.styleSheet() != dark and window.preferences().theme == 'light'

    window.shell.set_page('results')
    app.processEvents()
    assert window.shell.page == 'results' and window.queue_page.isVisible()
    assert window.preferences().route == 'results'
    assert not window.toolbar.add_files.isVisible() and not window.start.isVisible()


def test_narrow_window_settings_use_available_width(flat_window, sample):  # noqa: F811
    app, window = flat_window
    window.controller.import_sources((sample[1].media.path,))
    wait(app, lambda: not window.controller.busy)
    window.resize(900, 760)
    app.processEvents()
    assert not window.inspector.isVisible()
    window.inspector_toggle.click()
    app.processEvents()
    assert window.inspector.isVisible() and not window.sources.isVisible()
    assert window.inspector.scroll.horizontalScrollBar().maximum() == 0
    assert window.start.isVisible()
    window.inspector_toggle.click()
    assert window.sources.isVisible() and not window.inspector.isVisible()


def test_save_preset_from_result_when_source_is_offline(flat_window, sample, monkeypatch):  # noqa: F811
    app, window = flat_window
    source = sample[1].media.path
    window.controller.import_sources((source,))
    wait(app, lambda: not window.controller.busy)
    window.controller.prepare('start')
    wait(app, lambda: not window.controller.busy and bool(window.controller.queue.records) and not window.controller.queue.running)
    record = window.controller.queue.records[0]
    assert record.status is TaskStatus.COMPLETED, record.error
    frozen = record.plan
    source.rename(source.with_name('offline.wav'))
    window.shell.set_page('results')
    window.render()
    window.queue_page.table.selectRow(0)
    app.processEvents()
    monkeypatch.setattr(QInputDialog, 'getText', lambda *_args, **_kwargs: ('Archived recording', True))
    action = window.queue_page.buttons['save_preset']
    assert action.isEnabled()
    action.trigger()
    saved = window.named_presets['Archived recording']
    assert saved.operation is frozen.operation
    assert saved.track_rules[0].action == 'copy'
    assert record.plan is frozen and len(window.draft.outputs) == 1
