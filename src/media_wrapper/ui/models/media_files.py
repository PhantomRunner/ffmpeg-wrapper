"""Model-backed library; paths and inspection records remain in DesktopState."""
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, Qt


class MediaFileModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.paths: tuple[Path, ...] = ()
        self.labels: tuple[tuple[str, str], ...] = ()

    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.paths)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.paths):
            return None
        path = self.paths[index.row()]
        status, error = self.labels[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return f'{path.name}\n{status}'
        if role == Qt.ItemDataRole.ToolTipRole:
            return f'{path}\n{error or status}'
        if role == Qt.ItemDataRole.UserRole:
            return str(path)
        return None

    def update(self, paths, inspections) -> None:
        paths = tuple(paths)
        labels = tuple((inspections[p].status.value, inspections[p].error or '') if p in inspections
                       else ('Not inspected', '') for p in paths)
        if paths != self.paths:
            self.beginResetModel()
            self.paths, self.labels = paths, labels
            self.endResetModel()
        elif labels != self.labels:
            self.labels = labels
            if paths:
                self.dataChanged.emit(self.index(0), self.index(len(paths) - 1))
