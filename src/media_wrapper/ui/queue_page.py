"""Real queue/history projection and read-only selected-attempt details."""
import json
from dataclasses import asdict
from itertools import pairwise

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.capabilities import GPU_ENCODERS
from media_wrapper.domain.tasks import RETRYABLE, TERMINAL, TaskStatus
from media_wrapper.ui.models.tasks import (
    ProgressDelegate,
    TaskModel,
    TaskStatusDelegate,
)
from media_wrapper.ui.source_table import duration_text
from media_wrapper.ui.widgets.combo_box import ReadableComboBox
from media_wrapper.ui.widgets.controls import ActionButton


def size_text(size):
    if size is None:
        return '—'
    if size < 1024:
        return f'{size:,} B'
    for unit in ('KiB', 'MiB', 'GiB', 'TiB'):
        size /= 1024
        if size < 1024 or unit == 'TiB':
            return f'{size:,.1f} {unit}'


def verified_characteristics(record):
    if record.result is None:
        return '—'
    parts = [f'{record.result.format_name} · {", ".join(stream.codec for stream in record.result.streams)}']
    for stream in record.result.streams:
        if stream.kind == 'video' and stream.width and stream.height and not stream.is_artwork:
            parts.append(f'{stream.width}×{stream.height}' + (f' · {float(stream.frame_rate):.2f} fps' if stream.frame_rate else ''))
    if record.result.bit_rate:
        parts.append(f'{record.result.bit_rate / 1000:,.0f} kb/s')
    return ' · '.join(parts)


def result_values(record):
    source_size = record.plan.media.size_bytes
    output_size = record.result.size_bytes if record.result else None
    difference = '—'
    if source_size and output_size is not None:
        change = output_size - source_size
        difference = f'{"+" if change > 0 else "−" if change < 0 else ""}{size_text(abs(change))} · {output_size / source_size:.1%} of source'
    profiles = record.plan.streams
    requested = tuple(item.profile.encoder for item in profiles)
    args = record.commands[-1] if record.commands else record.command
    actual = tuple(value for flag, value in pairwise(args)
                   if flag == '-c' or (flag.startswith('-c:') and flag[3:].isdigit()))
    if actual == ('copy',):
        actual *= len(profiles)
    shown = actual if len(actual) == len(requested) else requested
    encoders = ', '.join(dict.fromkeys(
        f'{encoder} · CRF {item.profile.crf}' if item.profile.crf is not None else
        f'{encoder} · {item.profile.bitrate} kb/s configured' if item.profile.bitrate is not None else encoder
        for encoder, item in zip(shown, profiles, strict=True)
    ))
    return (record.plan.media.path.name, record.plan.output.path.name, record.status.value, size_text(source_size),
            size_text(output_size), difference, duration_text(record.elapsed_seconds),
            verified_characteristics(record), encoders, 'Verified' if record.result is not None else '—')


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
            if index.column() == 3 and record.status not in TERMINAL:
                stage = record.stage
                if record.pass_count > 1 and stage == 'Encoding':
                    stage = f'Pass {record.pass_index}/{record.pass_count}'
                if stage:
                    percent = record.progress.percent
                    return f'{stage} · {percent:.1f}%' if percent is not None else stage
            if index.column() == 4:
                return f'{record.progress.speed:.2f}×' if record.progress.speed is not None else 'Unknown'
            if index.column() == 5:
                elapsed = record.elapsed
                return f'{elapsed:.1f}s' if elapsed is not None and elapsed < 60 else duration_text(elapsed)
        return super().data(index, role)


class JobFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.status, self.query, self.results_only = 'All', '', False

    def filterAcceptsRow(self, row, parent):
        record = self.sourceModel().records[row]
        if self.results_only and record.status not in TERMINAL:
            return False
        states = {
            'All': set(TaskStatus), 'Queued': {TaskStatus.PENDING},
            'Running': {TaskStatus.PREPARING, TaskStatus.RUNNING}, 'Completed': {TaskStatus.COMPLETED},
            'Failed': {TaskStatus.FAILED}, 'Cancelled': {TaskStatus.CANCELLED},
            'Interrupted': {TaskStatus.INTERRUPTED}, 'History': TERMINAL,
        }
        text = f'{record.plan.media.path} {record.plan.output.path} {record.plan.operation.value} {record.status.value}'.casefold()
        return record.status in states.get(self.status, set(TaskStatus)) and self.query in text

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
        self._detail_record_id = None
        self._results_mode = False
        self._result_rows = ()
        self._queue = None
        self._busy = False
        row = QHBoxLayout()
        for name, text in (('start', 'Start queue'), ('stop', 'Stop after current'), ('cancel', 'Cancel selected'),
                           ('retry', 'Retry failed'), ('clear', 'Clear completed')):
            button = ActionButton(text, primary=name == 'start')
            button.clicked.connect(lambda _checked=False, name=name: self.action.emit(name))
            self.buttons[name] = button
            row.addWidget(button)
        more = QToolButton()
        more.setText('More actions')
        more.setAccessibleName('More queue actions')
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        for name, text in (('cancel_all', 'Cancel all'), ('retry_selected', 'Retry selected'),
                           ('cpu', 'Retry on CPU'), ('reuse', 'Edit as new output'), ('duplicate', 'Duplicate to workspace'),
                           ('up', 'Move pending up'), ('down', 'Move pending down'), ('remove', 'Remove pending'),
                           ('open', 'Open output folder'), ('open_file', 'Open output'), ('log', 'Open full log'),
                           ('load', 'Load queue…'), ('save', 'Save queue…'), ('history', 'Clear history…')):
            action = menu.addAction(text)
            action.triggered.connect(lambda _checked=False, name=name: self.action.emit(name))
            self.buttons[name] = action
        policy = menu.addMenu('On processing failure')
        self.policy_group = QActionGroup(self)
        for name, label in (('continue_on_error', 'Continue with next job'), ('stop_on_error', 'Stop the queue')):
            action = policy.addAction(label)
            action.setCheckable(True)
            self.policy_group.addAction(action)
            action.triggered.connect(lambda _checked=False, name=name: self.action.emit(name))
            self.buttons[name] = action
        more.setMenu(menu)
        row.addWidget(more)
        row.addStretch()
        layout.addLayout(row)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search filename, operation or output…')
        self.search.setAccessibleName('Search queue')
        self.filter = ReadableComboBox()
        self.filter.addItems(['All', 'Queued', 'Running', 'Completed', 'Failed', 'Cancelled', 'Interrupted', 'History'])
        self.filter.setAccessibleName('Job filter')
        filters.addWidget(self.search, 1)
        filters.addWidget(self.filter)
        layout.addLayout(filters)
        self.summary = QLabel('No jobs. Configure files in Workspace, then add them to the queue.')
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
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
        self.results = QTableWidget(0, 10)
        self.results.setHorizontalHeaderLabels(('Source', 'Output', 'State', 'Original', 'Result', 'Change',
                                                'Elapsed', 'Media properties', 'Encoding settings', 'Verification'))
        self.results.setAlternatingRowColors(True)
        self.results.setShowGrid(False)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setAccessibleName('Selected results comparison')
        self.results.verticalHeader().hide()
        self.details.addTab(self.results, 'Result comparison')
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

    def set_results_mode(self, enabled: bool):
        if self._results_mode == enabled:
            return
        self._results_mode = self.proxy.results_only = enabled
        self.search.setAccessibleName('Search results' if enabled else 'Search queue')
        for name in ('start', 'stop', 'cancel', 'cancel_all', 'up', 'down', 'remove', 'load', 'save',
                     'continue_on_error', 'stop_on_error'):
            self.buttons[name].setVisible(not enabled)
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItems(['All', *([] if enabled else ['Queued', 'Running']),
                              'Completed', 'Failed', 'Cancelled', 'Interrupted', 'History'])
        self.filter.blockSignals(False)
        self._filter()
        if self._queue is not None:
            self.render(self._queue, self._busy)

    def _filter(self, *_):
        self.proxy.configure(self.filter.currentText(), self.search.text())
        self.render_selection()
        if self._queue is not None:
            self._update_summary(self._queue)

    def selected_records(self):
        ids = {i.data(QueueModel.ID_ROLE) for i in self.table.selectionModel().selectedRows()}
        return tuple(r for r in self.model.records if r.id in ids)

    def filtered_records(self):
        ids = {self.proxy.index(row, 0).data(QueueModel.ID_ROLE) for row in range(self.proxy.rowCount())}
        return tuple(r for r in self.model.records if r.id in ids)

    def render(self, queue, busy=False):
        self._queue, self._busy = queue, busy
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
        self._update_summary(queue)
        pending = any(r.status == TaskStatus.PENDING for r in queue.records)
        self.buttons['start'].setEnabled(not queue.running and pending and not queue.persistence_error)
        self.buttons['stop'].setEnabled(queue.running and not queue.stop_requested)
        self.buttons['continue_on_error'].setChecked(not queue.stop_on_error)
        self.buttons['stop_on_error'].setChecked(queue.stop_on_error)
        self.buttons['cancel_all'].setEnabled(any(r.status not in TERMINAL for r in queue.records))
        self.buttons['save'].setEnabled(not busy and any(r.status != TaskStatus.COMPLETED for r in queue.records))
        self.buttons['load'].setEnabled(not busy and not queue.persistence_error)
        self.buttons['history'].setEnabled(any(r.status in TERMINAL for r in queue.records))
        self.render_selection()

    def _update_summary(self, queue):
        records = self.filtered_records()
        counts = {state: sum(r.status == state for r in records) for state in TaskStatus}
        details = [f'{state.value}: {count}' for state, count in counts.items() if count]
        if self._results_mode:
            completed = [r for r in records if r.result is not None and r.result.size_bytes is not None]
            if completed:
                output_size = sum(r.result.size_bytes for r in completed)
                sources = {r.plan.media.path: r.plan.media.size_bytes for r in completed}
                original = (f'{size_text(sum(sources.values()))} original → '
                            if all(size is not None for size in sources.values()) else '')
                details.append(f'{original}{size_text(output_size)} verified output')
        elif queue.running:
            batch = tuple(r for r in queue.records if r.id in queue.batch_ids)
            active = queue.active.record if queue.active is not None else None
            finished = sum(r.status in TERMINAL for r in batch)
            if batch:
                details.append(f'{finished}/{len(batch)} attempts finished')
                if active and active.id in queue.batch_ids and active.progress.percent is not None:
                    fraction = (max(0, active.pass_index - 1) + active.progress.percent / 100) / active.pass_count
                    batch_percent = (finished + min(0.999, max(0, fraction))) / len(batch) * 100
                    details.append(f'{batch_percent:.1f}% estimated batch work')
            if active and active.progress.eta is not None and active.pass_index == active.pass_count and active.stage == 'Encoding':
                details.append(f'Current encode ETA {duration_text(active.progress.eta)}')
            if queue.stop_requested:
                details.append('Stops after the current job')
        if queue.persistence_error:
            details.append(queue.persistence_error)
        if queue.runtime_notice:
            details.append(queue.runtime_notice)
        empty = 'No results. Verified outputs and other attempts appear here.' if self._results_mode else (
            'No jobs. Configure files in Workspace, then add them to the queue.')
        self.summary.setText(' · '.join(details) if details else empty)

    def render_selection(self, *_):
        selected = self.selected_records()
        filtered = self.filtered_records()
        self.buttons['cancel'].setEnabled(any(r.status not in TERMINAL for r in selected))
        self.buttons['retry'].setEnabled(any(r.status in {TaskStatus.FAILED, TaskStatus.INTERRUPTED} for r in filtered))
        self.buttons['retry_selected'].setEnabled(any(r.status in RETRYABLE for r in selected))
        self.buttons['clear'].setEnabled(any(r.status == TaskStatus.COMPLETED for r in filtered))
        self.buttons['cpu'].setEnabled(any(r.status in RETRYABLE
                                         and any(s.profile.encoder in GPU_ENCODERS for s in r.plan.streams) for r in selected))
        single = selected[0] if len(selected) == 1 else None
        pending = tuple(r.id for r in self.model.records if r.status == TaskStatus.PENDING)
        self.buttons['up'].setEnabled(single is not None and single.id in pending[1:])
        self.buttons['down'].setEnabled(single is not None and single.id in pending[:-1])
        self.buttons['remove'].setEnabled(any(r.status == TaskStatus.PENDING for r in selected))
        self.buttons['reuse'].setEnabled(single is not None and single.status in RETRYABLE)
        self.buttons['duplicate'].setEnabled(single is not None and single.status in TERMINAL)
        self.buttons['open'].setEnabled(single is not None and single.status == TaskStatus.COMPLETED and single.result is not None)
        self.buttons['open_file'].setEnabled(self.buttons['open'].isEnabled())
        self.buttons['log'].setEnabled(single is not None and single.log_path is not None and single.log_path.is_file())

        self._render_results(selected)
        if single is None:
            for widget in (self.settings, self.commands, self.logs):
                widget.setPlainText(f'{len(selected)} jobs selected.' if selected else 'Select a job to inspect its settings, commands and logs.')
            return
        record = single
        changed_selection = self._detail_record_id != record.id
        self._detail_record_id = record.id
        settings = json.dumps({'settings': asdict(record.plan), 'verified_result': asdict(record.result) if record.result else None,
                               'partial_output': str(record.partial_path) if record.partial_path and record.status in RETRYABLE else None,
                               'created_at': record.created_at,
                               'started_at': record.started_at, 'finished_at': record.finished_at,
                               'elapsed_seconds': record.elapsed, 'ffmpeg_build': record.binary_version},
                              default=str, ensure_ascii=False, indent=2)
        commands = record.commands or ((record.command,) if record.command else ())
        values = ((self.settings, settings), (self.commands, json.dumps(commands, ensure_ascii=False, indent=2)),
                  (self.logs, '\n'.join(filter(None, (record.error, record.failure_detail, record.log_error, record.log)))))
        for widget, text in values:
            if widget.toPlainText() != text:
                scrollbar = widget.verticalScrollBar()
                at_end = scrollbar.value() == scrollbar.maximum()
                position = scrollbar.value()
                widget.setPlainText(text)
                if widget is self.logs and at_end:
                    scrollbar.setValue(scrollbar.maximum())
                else:
                    scrollbar.setValue(0 if changed_selection else position)

    def _render_results(self, selected):
        rows = tuple(result_values(record) for record in selected)
        if rows == self._result_rows:
            return
        self._result_rows = rows
        self.results.setRowCount(len(rows))
        for row, (record, values) in enumerate(zip(selected, rows, strict=True)):
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                tooltip = str(record.plan.output.path) if column == 1 else value
                item.setToolTip(tooltip)
                self.results.setItem(row, column, item)
        self.results.resizeColumnsToContents()
