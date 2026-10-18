"""Accessible queue projection with real progress values and stable attempt IDs."""
from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QStyledItemDelegate

from media_wrapper.ui.theme.tokens import COLORS


class TaskModel(QAbstractTableModel):
    HEADERS = ('Source / operation', 'Output', 'State', 'Progress', 'Speed / ETA')

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.records = ()
        self.ids = ()

    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.records)

    def columnCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.records):
            return None
        record = self.records[index.row()]
        progress = record.progress
        if role == Qt.ItemDataRole.UserRole:
            return progress.percent if index.column() == 3 else record.id
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole, Qt.ItemDataRole.ToolTipRole):
            codecs = ', '.join(s.profile.encoder for s in record.plan.streams)
            values = (f'{record.plan.media.path.name} · {record.plan.operation.value} · {codecs}',
                      str(record.plan.output.path), record.status.value,
                      f'{progress.percent:.1f}%' if progress.percent is not None else 'Unknown',
                      (f'{progress.speed:.2f}×' if progress.speed is not None else 'Speed unknown') + ' / ' +
                      (f'{progress.eta:.0f} s' if progress.eta is not None else 'ETA unknown'))
            if role == Qt.ItemDataRole.ToolTipRole and index.column() == 0:
                return str(record.plan.media.path) + '\n' + values[0]
            return values[index.column()]
        return None

    def update(self, records) -> None:
        ids = tuple(r.id for r in records)
        if ids != self.ids:
            self.beginResetModel()
            self.records, self.ids = tuple(records), ids
            self.endResetModel()
        else:
            self.records = tuple(records)
            if records:
                self.dataChanged.emit(self.index(0, 0), self.index(len(records) - 1, len(self.HEADERS) - 1))


class ProgressDelegate(QStyledItemDelegate):
    """Static progress tracks; unknown progress uses a dashed outline, never fake fill."""
    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)
        rect = option.rect.adjusted(5, option.rect.height() - 7, -5, -2)
        painter.save()
        painter.setPen(QColor(COLORS['secondary']))
        painter.setBrush(QColor(COLORS['control']))
        value = index.data(Qt.ItemDataRole.UserRole)
        if value is None:
            pen = painter.pen()
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)
        else:
            painter.fillRect(rect, QColor(COLORS['control']))
            rect.setWidth(round(rect.width() * max(0, min(100, value)) / 100))
            painter.fillRect(rect, QColor(COLORS['accent']))
        painter.restore()
