"""Dense source model/view with stable identities through sorting and filtering."""
from PySide6.QtCore import QAbstractTableModel, QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.draft import default_options
from media_wrapper.domain.inspection import InspectionStatus
from media_wrapper.ui.inspection_presenter import format_inspection


def duration_text(seconds):
    if seconds is None:
        return 'Unknown'
    seconds = int(seconds)
    return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'


def size_text(size):
    if size is None:
        return 'Unknown'
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if size < 1024 or unit == 'TiB':
            return f'{size:.1f} {unit}'
        size /= 1024


class SourceModel(QAbstractTableModel):
    inclusion_changed = Signal(str, bool)
    ID_ROLE = Qt.ItemDataRole.UserRole + 10
    SORT_ROLE = Qt.ItemDataRole.UserRole + 11
    HEADERS = ('', 'Name', 'Format', 'Duration', 'Size', 'Codec', 'Status', 'Overrides')

    def __init__(self, draft, parent=None):
        super().__init__(parent)
        self.draft = draft
        self.ids = ()
        self.statuses = {}
        self._row_cache = ()
        self._operation = None

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.ids)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]

    def flags(self, index):
        flags = super().flags(index)
        return flags | Qt.ItemFlag.ItemIsUserCheckable if index.column() == 0 else flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if (index.isValid() and index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole
                and 0 <= index.row() < len(self.ids) and self.ids[index.row()] in self.draft.items):
            included = value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value)
            self.inclusion_changed.emit(self.ids[index.row()], included)
            self.dataChanged.emit(index, index)
            return True
        return False

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.ids):
            return None
        if role == self.ID_ROLE:
            return self.ids[index.row()]
        item = self.draft.items.get(self.ids[index.row()])
        if item is None:
            return None  # A coalesced structural refresh may still be queued.
        media = item.media
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == 0:
            return Qt.CheckState.Checked if item.included else Qt.CheckState.Unchecked
        if role == self.SORT_ROLE and index.column() == 1:
            return item.path.name.casefold()
        status = self.statuses.get(item.id)
        if not status:
            status = ('Not inspected' if not item.inspection else
                      {InspectionStatus.PENDING: 'Waiting for probe', InspectionStatus.RUNNING: 'Probing',
                       InspectionStatus.COMPLETED: 'Not validated', InspectionStatus.FAILED: 'Probe failed',
                       InspectionStatus.CANCELLED: 'Probe cancelled'}[item.inspection.status])
        options = item.options.get(self.draft.operation)
        baseline = item.defaults.get(self.draft.operation)
        if baseline is None and media:
            baseline = default_options(media, self.draft.operation)
        modified = bool(options and baseline and options != baseline)
        values = ('', item.path.name, media.format_name if media else '—',
                  duration_text(media.duration) if media else '—', size_text(media.size_bytes) if media else '—',
                  ', '.join(dict.fromkeys(s.codec for s in media.streams)) if media else '—', status,
                  (options.preset_name or 'Custom') if modified else '—')
        if role == self.SORT_ROLE:
            if index.column() == 3:
                return media.duration if media and media.duration is not None else -1.0
            if index.column() == 4:
                return media.size_bytes if media and media.size_bytes is not None else -1
            return values[index.column()].casefold()
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(item.path) + '\n' + (item.inspection.error or status if item.inspection else status)
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return values[index.column()] if index.column() else ('Included' if item.included else 'Excluded') if role == Qt.ItemDataRole.AccessibleTextRole else ''

    def refresh(self):
        ids = tuple(self.draft.items)
        cache = tuple((self.draft.items[item_id].revision, self.statuses.get(item_id)) for item_id in ids)
        if ids != self.ids:
            self.beginResetModel()
            self.ids = ids
            self.endResetModel()
        elif ids:
            if self._operation != self.draft.operation:
                self.dataChanged.emit(self.index(0, 0), self.index(len(ids) - 1, len(self.HEADERS) - 1))
            else:
                for row, value in enumerate(cache):
                    if row >= len(self._row_cache) or value != self._row_cache[row]:
                        self.dataChanged.emit(self.index(row, 0), self.index(row, len(self.HEADERS) - 1))
        self._row_cache, self._operation = cache, self.draft.operation


class SourceTable(QWidget):
    selection_changed = Signal(object)
    files_dropped = Signal(object)

    def __init__(self, draft, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Filter input files…')
        self.search.setAccessibleName('Filter input files')
        layout.addWidget(self.search)
        self.empty = QLabel('Add files or drop a folder to begin.\nRemux, compress or convert local media files.')
        self.empty.setWordWrap(True)
        self.empty.setProperty('role', 'sourceSummary')
        layout.addWidget(self.empty)
        self.table = QTableView()
        self.table.setAccessibleName('Input files: check to include, select rows to inspect or edit')
        self.model = SourceModel(draft, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(SourceModel.SORT_ROLE)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(38)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 34), (2, 75), (3, 90), (4, 90), (5, 110), (6, 125), (7, 85)):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 3)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName('Selected source details and streams')
        self.details.setMinimumHeight(90)
        self.details.setMaximumHeight(210)
        layout.addWidget(self.details, 1)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.table.selectionModel().selectionChanged.connect(self._selection)

    def selected_ids(self):
        return tuple(index.data(SourceModel.ID_ROLE) for index in self.table.selectionModel().selectedRows())

    def _selection(self, *_):
        ids = self.selected_ids()
        self.selection_changed.emit(ids)
        self.show_details(ids)

    def show_details(self, ids=None):
        ids = self.selected_ids() if ids is None else ids
        items = [self.model.draft.items[i] for i in ids if i in self.model.draft.items]
        text = 'Select a source to inspect its metadata.'
        if len(items) == 1:
            item = items[0]
            text = str(item.path) + '\n\n' + (format_inspection(item.media) if item.media else
                   item.inspection.error or item.inspection.status.value if item.inspection else 'Not inspected')
        elif items:
            text = f'{len(items)} files selected · {sum(i.included for i in items)} included\n'
            text += '\n'.join(str(i.path) for i in items[:20])
            if len(items) > 20:
                text += '\n…'
        if self.details.toPlainText() != text:
            self.details.setPlainText(text)

    def refresh(self):
        selected = set(self.selected_ids())
        structural = tuple(self.model.draft.items) != self.model.ids
        self.model.refresh()
        if structural:
            selection = self.table.selectionModel()
            from PySide6.QtCore import QItemSelectionModel
            for row in range(self.proxy.rowCount()):
                index = self.proxy.index(row, 0)
                if index.data(SourceModel.ID_ROLE) in selected:
                    selection.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.empty.setVisible(not self.model.ids)
        self.table.setVisible(bool(self.model.ids))
        self.show_details()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for column in (2, 5, 7):
            self.table.setColumnHidden(column, self.width() < 660)

    def dragEnterEvent(self, event):
        if event.mimeData().urls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        from pathlib import Path
        urls = event.mimeData().urls()
        if urls and all(u.isLocalFile() for u in urls):
            self.files_dropped.emit(tuple(Path(u.toLocalFile()) for u in urls))
            event.acceptProposedAction()
