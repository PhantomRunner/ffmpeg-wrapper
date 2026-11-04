from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from media_wrapper.domain.draft import DraftState
from media_wrapper.ui.source_table import SourceModel, SourceTable


def test_ten_thousand_rows_sort_and_include_by_identity(tmp_path):
    app = QApplication.instance() or QApplication([])
    draft = DraftState()
    draft.add(tuple(tmp_path / f'{i:05}.mkv' for i in range(10000)))
    view = SourceTable(draft)
    view.model.inclusion_changed.connect(draft.include)
    view.refresh()
    assert view.model.rowCount() == 10000
    view.proxy.sort(1, Qt.SortOrder.DescendingOrder)
    index = view.proxy.index(0, 0)
    item_id = index.data(SourceModel.ID_ROLE)
    assert draft.items[item_id].path.name == '09999.mkv'
    view.proxy.setData(index, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    assert not draft.items[item_id].included
    view.table.selectRow(0)
    assert view.selected_ids() == (item_id,)
    view.search.setText('09999')
    assert view.proxy.rowCount() == 1
    assert view.proxy.index(0, 0).data(SourceModel.ID_ROLE) == item_id
    resets = []
    view.model.modelReset.connect(lambda: resets.append(True))
    view.refresh()
    assert not resets
    view.close()
    app.processEvents()
