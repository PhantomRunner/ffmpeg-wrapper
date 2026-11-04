"""Real queue/history projection and read-only selected-attempt details."""
import json
from dataclasses import asdict

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QTableView,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.capabilities import GPU_ENCODERS
from media_wrapper.domain.tasks import TaskStatus
from media_wrapper.ui.models.tasks import (
    ProgressDelegate,
    TaskModel,
    TaskStatusDelegate,
)
from media_wrapper.ui.source_table import duration_text
from media_wrapper.ui.widgets.combo_box import ReadableComboBox
from media_wrapper.ui.widgets.controls import ActionButton

TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


class QueueModel(TaskModel):
    HEADERS = ('Source / operation', 'Output', 'State', 'Progress', 'Speed', 'Elapsed')
    ID_ROLE = Qt.ItemDataRole.UserRole + 10

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        record = self.records[index.row()]
        if role == self.ID_ROLE:
            return record.id
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole, Qt.ItemDataRole.ToolTipRole):
            if index.column() == 2 and getattr(record, 'cancel_requested', False) and record.status not in TERMINAL:
                return 'Cancelling'
            if index.column() == 3 and getattr(record, 'pass_count', 1) > 1:
                percent = f'{record.progress.percent:.1f}%' if record.progress.percent is not None else 'Unknown'
                return f'Pass {record.pass_index}/{record.pass_count} · {percent}'
            if index.column() == 4:
                return f'{record.progress.speed:.2f}×' if record.progress.speed is not None else 'Unknown'
            if index.column() == 5:
                return duration_text(getattr(record, 'elapsed', None))
        return super().data(index, role)


class JobFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.status, self.query = 'All', ''

    def filterAcceptsRow(self, row, parent):
        record = self.sourceModel().records[row]
        states = {
            'All': set(TaskStatus), 'Queued': {TaskStatus.PENDING},
            'Running': {TaskStatus.PREPARING, TaskStatus.RUNNING}, 'Completed': {TaskStatus.COMPLETED},
            'Failed': {TaskStatus.FAILED}, 'Cancelled': {TaskStatus.CANCELLED}, 'History': TERMINAL,
        }
        text = f'{record.plan.media.path} {record.plan.output.path} {record.plan.operation.value} {record.status.value}'.casefold()
        return record.status in states[self.status] and self.query in text

    def configure(self, status, query):
        self.status, self.query = status, query.casefold()
        self.invalidateFilter()


class QueuePage(QWidget):
    action = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.buttons = {}
        for actions in ((('start', 'Start queue'), ('cancel', 'Cancel selected'), ('retry', 'Retry failed'),
                         ('clear', 'Clear completed')),
                        (('cancel_all', 'Cancel all'), ('cpu', 'Retry on CPU'), ('open', 'Open output folder'),
                         ('load', 'Load queue…'), ('save', 'Save queue…'), ('history', 'Clear history…'))):
            row = QHBoxLayout()
            for name, text in actions:
                button = ActionButton(text, primary=name == 'start')
                button.clicked.connect(lambda _checked=False, name=name: self.action.emit(name))
                self.buttons[name] = button
                row.addWidget(button)
            row.addStretch()
            layout.addLayout(row)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search filename, operation or output…')
        self.search.setAccessibleName('Search queue')
        self.filter = ReadableComboBox()
        self.filter.addItems(['All', 'Queued', 'Running', 'Completed', 'Failed', 'Cancelled', 'History'])
        self.filter.setAccessibleName('Job filter')
        filters.addWidget(self.search, 1)
        filters.addWidget(self.filter)
        layout.addLayout(filters)
        self.summary = QLabel('No jobs. Configure files in Workspace, then add them to the queue.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableView()
        self.table.setAccessibleName('Queue and history jobs')
        self.model = QueueModel(self)
        self.proxy = JobFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table.setModel(self.proxy)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(3, 165)
        self.table.setItemDelegateForColumn(2, TaskStatusDelegate(self.table))
        self.table.setItemDelegateForColumn(3, ProgressDelegate(self.table))
        self.details = QTabWidget()
        self.settings, self.commands, self.logs = QTextEdit(), QTextEdit(), QTextEdit()
        for name, widget in (('Frozen settings', self.settings), ('Executed commands', self.commands), ('Logs / errors', self.logs)):
            widget.setReadOnly(True)
            widget.setProperty('role', 'code')
            widget.setAccessibleName(name)
            self.details.addTab(widget, name)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setSizes([500, 230])
        layout.addWidget(splitter, 1)
        self.search.textChanged.connect(self._filter)
        self.filter.currentTextChanged.connect(self._filter)
        self.table.selectionModel().selectionChanged.connect(self.render_selection)

    def _filter(self, *_):
        self.proxy.configure(self.filter.currentText(), self.search.text())
        self.render_selection()

    def selected_records(self):
        ids = {i.data(QueueModel.ID_ROLE) for i in self.table.selectionModel().selectedRows()}
        return tuple(r for r in self.model.records if r.id in ids)

    def filtered_records(self):
        ids = {self.proxy.index(row, 0).data(QueueModel.ID_ROLE) for row in range(self.proxy.rowCount())}
        return tuple(r for r in self.model.records if r.id in ids)

    def render(self, queue, busy=False):
        selected = {r.id for r in self.selected_records()}
        structural = self.model.ids != tuple(r.id for r in queue.records)
        self.model.update(queue.records)
        if structural:
            from PySide6.QtCore import QItemSelectionModel
            for row in range(self.proxy.rowCount()):
                index = self.proxy.index(row, 0)
                if index.data(QueueModel.ID_ROLE) in selected:
                    self.table.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        if not self.selected_records() and self.proxy.rowCount():
            self.table.selectRow(0)
        counts = {state: sum(r.status == state for r in queue.records) for state in TaskStatus}
        self.summary.setText(' · '.join(f'{state.value}: {n}' for state, n in counts.items() if n) or
                             'No jobs. Configure files in Workspace, then add them to the queue.')
        self.buttons['start'].setEnabled(not queue.running and any(r.status == TaskStatus.PENDING for r in queue.records))
        self.buttons['cancel_all'].setEnabled(any(r.status not in TERMINAL for r in queue.records))
        self.buttons['save'].setEnabled(not busy and any(r.status != TaskStatus.COMPLETED for r in queue.records))
        self.buttons['load'].setEnabled(not busy)
        self.buttons['history'].setEnabled(any(r.status in TERMINAL for r in queue.records))
        self.render_selection()

    def render_selection(self, *_):
        selected = self.selected_records()
        filtered = self.filtered_records()
        self.buttons['cancel'].setEnabled(any(r.status not in TERMINAL for r in selected))
        self.buttons['retry'].setEnabled(any(r.status == TaskStatus.FAILED for r in filtered))
        self.buttons['clear'].setEnabled(any(r.status == TaskStatus.COMPLETED for r in filtered))
        self.buttons['cpu'].setEnabled(any(r.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)
                                         and any(s.profile.encoder in GPU_ENCODERS for s in r.plan.streams) for r in selected))
        self.buttons['open'].setEnabled(len(selected) == 1 and selected[0].status == TaskStatus.COMPLETED and selected[0].result is not None)
        if len(selected) != 1:
            for widget in (self.settings, self.commands, self.logs):
                widget.setPlainText(f'{len(selected)} jobs selected.' if selected else 'Select a job to inspect its settings, commands and logs.')
            return
        record = selected[0]
        settings = json.dumps(asdict(record.plan), default=str, ensure_ascii=False, indent=2)
        commands = getattr(record, 'commands', ()) or ((record.command,) if record.command else ())
        values = ((self.settings, settings), (self.commands, json.dumps(commands, ensure_ascii=False, indent=2)),
                  (self.logs, '\n'.join(filter(None, (record.error, record.failure_detail, record.log)))))
        for widget, text in values:
            if widget.toPlainText() != text:
                scrollbar = widget.verticalScrollBar()
                at_end = scrollbar.value() == scrollbar.maximum()
                widget.setPlainText(text)
                if at_end:
                    scrollbar.setValue(scrollbar.maximum())
