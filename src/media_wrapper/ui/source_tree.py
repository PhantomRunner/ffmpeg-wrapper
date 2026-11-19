"""Source and output rows with independent focus, selection and inclusion."""
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import (
    QAbstractItemModel,
    QItemSelectionModel,
    QModelIndex,
    QSignalBlocker,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.inspection import InspectionStatus
from media_wrapper.ui.source_table import SourceModel, duration_text, size_text

_ROOT = QModelIndex()


@dataclass(eq=False)
class _Row:
    id: str
    row: int
    parent: '_Row | None' = None
    children: list['_Row'] = field(default_factory=list)


class SourceTreeModel(QAbstractItemModel):
    inclusion_changed = Signal(str, bool)
    HEADERS = ('Include', 'Source / output', 'Status')
    ID_ROLE = SourceModel.ID_ROLE
    SORT_ROLE = SourceModel.SORT_ROLE
    SOURCE_ROLE = Qt.ItemDataRole.UserRole + 12
    OUTPUT_ROLE = Qt.ItemDataRole.UserRole + 13

    def __init__(self, draft, parent=None):
        super().__init__(parent)
        self.draft = draft
        self._view_parent = parent
        self.rows = []
        self.nodes = {}
        self.statuses = {}
        self._structure = ()
        self._cache = {}

    def columnCount(self, parent=_ROOT):
        return len(self.HEADERS)

    def rowCount(self, parent=_ROOT):
        if not parent.isValid():
            return len(self.rows)
        return len(parent.internalPointer().children) if parent.column() == 0 else 0

    def index(self, row, column, parent=_ROOT):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        rows = parent.internalPointer().children if parent.isValid() else self.rows
        return self.createIndex(row, column, rows[row])

    def parent(self, index):
        if index.isValid() and (parent := index.internalPointer().parent) is not None:
            return self.createIndex(parent.row, 0, parent)
        return QModelIndex()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def flags(self, index):
        flags = super().flags(index)
        return flags | Qt.ItemFlag.ItemIsUserCheckable if index.isValid() and index.column() == 0 else flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.column() != 0 or role != Qt.ItemDataRole.CheckStateRole:
            return False
        node = index.internalPointer()
        included = value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value)
        self.inclusion_changed.emit(node.id, included)
        self.refresh()
        return True

    def index_for_id(self, row_id, column=0):
        node = self.nodes.get(row_id)
        return self.createIndex(node.row, column, node) if node else QModelIndex()

    def structure(self):
        return tuple((source_id, tuple(output.id for output in self.draft.outputs_for(source_id)))
                     for source_id in self.draft.items)

    def refresh(self, structure=None):
        structure = self.structure() if structure is None else structure
        structural = structure != self._structure
        if structural:
            self.beginResetModel()
            self.rows.clear()
            self.nodes.clear()
            for source_id, outputs in structure:
                parent = _Row(source_id, len(self.rows))
                self.rows.append(parent)
                self.nodes[source_id] = parent
                for output_id in outputs:
                    child = _Row(output_id, len(parent.children), parent)
                    parent.children.append(child)
                    self.nodes[output_id] = child
            self._structure = structure
            self._cache.clear()
            self.endResetModel()
        for source_id, output_ids in structure:
            item = self.draft.items[source_id]
            check = tuple(self.draft.outputs[output_id].included for output_id in output_ids)
            self._update(source_id, (item.revision, check), notify=not structural)
            for output_id in output_ids:
                output = self.draft.outputs[output_id]
                self._update(output_id, (output.revision, output.label, output.included, output.operation,
                                         self.statuses.get(output_id), item.revision), notify=not structural)

    def _update(self, row_id, key, *, notify):
        if self._cache.get(row_id) != key:
            self._cache[row_id] = key
            if notify:
                self.dataChanged.emit(self.index_for_id(row_id), self.index_for_id(row_id, len(self.HEADERS) - 1))

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = index.internalPointer()
        output = self.draft.outputs.get(node.id) if node.parent else None
        item = self.draft.items.get(node.parent.id if node.parent else node.id)
        if item is None or (node.parent and output is None):
            return None
        if role == self.ID_ROLE:
            return node.id
        if role == self.SOURCE_ROLE:
            return item.id
        if role == self.OUTPUT_ROLE:
            return output.id if output else None
        if role in (Qt.ItemDataRole.CheckStateRole, Qt.ItemDataRole.AccessibleTextRole) and index.column() == 0:
            state = self._check_state(item.id, output)
            if role == Qt.ItemDataRole.CheckStateRole:
                return state
            return {Qt.CheckState.Unchecked: 'Excluded', Qt.CheckState.PartiallyChecked: 'Partially included',
                    Qt.CheckState.Checked: 'Included'}[state]
        if output:
            status = self.statuses.get(output.id, 'Draft') if item.inspected else self._source_status(item)
            option = output.options.get(output.operation)
            name = output.label
            if not name or name == f'Output {output.number}':
                name = option.preset_name if option and option.preset_name else f'Output {output.number} · {output.operation.value.title()}'
            values = ('', name, status)
            detail = f'{item.path}\n{output.operation.value.title()} · {status}'
        else:
            status = self._source_status(item)
            media = item.media
            codecs = ', '.join(dict.fromkeys(stream.codec for stream in media.streams)) if media else ''
            values = ('', item.path.name, status)
            detail = '\n'.join(str(part) for part in (item.path, status, codecs,
                               duration_text(media.duration) if media else '', size_text(media.size_bytes) if media else '') if part)
            if item.inspection and item.inspection.error:
                detail += f'\n{item.inspection.error}'
        if role == Qt.ItemDataRole.ToolTipRole:
            return detail
        if role == Qt.ItemDataRole.ForegroundRole and index.column() == 2:
            state = status.split(':', 1)[0]
            color = {'Ready': 'success', 'Added to queue': 'processing', 'Warning': 'warning', 'Error': 'error',
                     'Unsupported / probe failed': 'error'}.get(state)
            if color and self._view_parent:
                palette = self._view_parent.window().property('themeStatusColors') or {}
                if color in palette:
                    return QColor(palette[color])
        if role == self.SORT_ROLE and index.column() == 0:
            return self._check_state(item.id, output).value
        if role == self.SORT_ROLE:
            return values[index.column()].casefold()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return values[index.column()]
        return None

    def _check_state(self, source_id, output):
        states = (output.included,) if output else tuple(o.included for o in self.draft.outputs_for(source_id))
        return (Qt.CheckState.Checked if all(states) and states else Qt.CheckState.PartiallyChecked if any(states)
                else Qt.CheckState.Unchecked)

    def _source_status(self, item):
        if item.inspected:
            count = len(self.draft.outputs_for(item.id))
            return f'{count} output' + ('s' if count != 1 else '')
        if item.inspection:
            return {InspectionStatus.PENDING: 'Waiting for probe', InspectionStatus.RUNNING: 'Probing',
                    InspectionStatus.COMPLETED: 'Inspected', InspectionStatus.FAILED: 'Unsupported / probe failed',
                    InspectionStatus.CANCELLED: 'Probe cancelled'}[item.inspection.status]
        return 'Not inspected'


class _SourceView(QTreeView):
    def selectRow(self, row):
        index = self.model().index(row, 0)
        self.selectionModel().setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect |
                                              QItemSelectionModel.SelectionFlag.Rows)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and (index := self.currentIndex()).isValid():
            check = index.siblingAtColumn(0)
            state = check.data(Qt.ItemDataRole.CheckStateRole)
            value = Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked
            self.model().setData(check, value, Qt.ItemDataRole.CheckStateRole)
            event.accept()
            return
        super().keyPressEvent(event)


class SourceTree(QWidget):
    selection_changed = Signal(object)
    output_focused = Signal(str)
    source_inspected = Signal(str)
    files_dropped = Signal(object)

    def __init__(self, draft, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._expanded = set()
        self._selected = ()
        self._current = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search imported media…')
        self.search.setAccessibleName('Search sources and outputs')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.empty = QLabel('Add media files or drop a folder to begin.')
        self.empty.setWordWrap(True)
        self.empty.setProperty('role', 'sourceSummary')
        layout.addWidget(self.empty)
        self.table = _SourceView()
        self.table.setObjectName('workspaceOutputTree')
        self.table.setAccessibleName('Sources and their outputs')
        self.table.setAccessibleDescription('Expand a source to select an output. Space toggles inclusion.')
        self.model = SourceTreeModel(draft, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(SourceTreeModel.SORT_ROLE)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setAutoAcceptChildRows(True)
        self.table.setModel(self.proxy)
        self.table.setTreePosition(1)
        self.table.setAllColumnsShowFocus(True)
        self.table.setUniformRowHeights(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        header = self.table.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 68)
        self.table.setColumnWidth(2, 142)
        layout.addWidget(self.table, 1)
        selection = self.table.selectionModel()
        selection.selectionChanged.connect(self._selection)
        selection.currentChanged.connect(self._focus)
        self.table.expanded.connect(lambda index: self._expanded.add(index.data(SourceTreeModel.ID_ROLE)))
        self.table.collapsed.connect(lambda index: self._expanded.discard(index.data(SourceTreeModel.ID_ROLE)))
        self.table.doubleClicked.connect(self._inspect)
        self.search.textChanged.connect(self._filter)

    def row_ids(self):
        return self._selected

    def selected_ids(self):
        draft = self.model.draft
        return tuple(dict.fromkeys(draft.outputs[row].source_id if row in draft.outputs else row
                                   for row in self._selected if row in self.model.nodes))

    def selected_output_ids(self):
        draft = self.model.draft
        ids = (row_id for row in self._selected if row in self.model.nodes for row_id in
               ((row,) if row in draft.outputs else tuple(output.id for output in draft.outputs_for(row))))
        return tuple(dict.fromkeys(ids))

    def current_source_id(self):
        return self.table.currentIndex().data(SourceTreeModel.SOURCE_ROLE)

    def select_id(self, row_id):
        index = self.proxy.mapFromSource(self.model.index_for_id(row_id))
        if not index.isValid():
            return False
        if index.parent().isValid():
            self.table.expand(index.parent())
        selection = self.table.selectionModel()
        selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)
        self.table.scrollTo(index)
        return True

    def _selection(self, *_):
        self._selected = tuple(index.data(SourceTreeModel.ID_ROLE) for index in self.table.selectionModel().selectedRows())
        self.selection_changed.emit(self.selected_ids())

    def _focus(self, index, _previous):
        if not index.isValid():
            return
        self._current = index.data(SourceTreeModel.ID_ROLE)
        if output_id := index.data(SourceTreeModel.OUTPUT_ROLE):
            self.output_focused.emit(output_id)
        elif source_id := index.data(SourceTreeModel.SOURCE_ROLE):
            active = self.model.draft.outputs.get(self.model.draft.active_output_id)
            if active is None or active.source_id != source_id:
                outputs = self.model.draft.outputs_for(source_id)
                if outputs:
                    self.output_focused.emit(outputs[0].id)

    def _inspect(self, index):
        if source_id := index.data(SourceTreeModel.SOURCE_ROLE):
            self.source_inspected.emit(source_id)

    def _filter(self, query):
        with QSignalBlocker(self.table.selectionModel()), QSignalBlocker(self.table):
            self.proxy.setFilterFixedString(query)
            self._restore()
            if query:
                self.table.expandAll()
        self.empty.setVisible(self.proxy.rowCount() == 0)
        self.empty.setText('No sources or outputs match your search.' if query else 'Add media files or drop a folder to begin.')
        self.table.setVisible(bool(self.proxy.rowCount()))

    def _restore(self):
        selection = self.table.selectionModel()
        for row_id in self._expanded:
            index = self.proxy.mapFromSource(self.model.index_for_id(row_id))
            if index.isValid():
                self.table.expand(index)
        for row_id in self._selected:
            index = self.proxy.mapFromSource(self.model.index_for_id(row_id))
            if index.isValid():
                selection.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        current = self.proxy.mapFromSource(self.model.index_for_id(self._current))
        if current.isValid():
            selection.setCurrentIndex(current, QItemSelectionModel.SelectionFlag.NoUpdate)

    def refresh(self):
        structure = self.model.structure()
        structural = structure != self.model._structure
        if structural:
            previous = self.model.nodes.copy()
            with QSignalBlocker(self.table.selectionModel()), QSignalBlocker(self.table):
                self.model.refresh(structure)
                self._selected = tuple(row for row in self._selected if row in self.model.nodes)
                self._expanded &= self.model.nodes.keys()
                self._expanded.update(row.id for row in self.model.rows if row.id not in previous)
                self._restore()
        else:
            self.model.refresh(structure)
        visible = self.proxy.rowCount() > 0
        self.empty.setVisible(not visible)
        self.table.setVisible(visible)
        if structural:
            self.selection_changed.emit(self.selected_ids())

    def dragEnterEvent(self, event):
        if event.mimeData().urls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and all(url.isLocalFile() for url in urls):
            self.files_dropped.emit(tuple(Path(url.toLocalFile()) for url in urls))
            event.acceptProposedAction()
