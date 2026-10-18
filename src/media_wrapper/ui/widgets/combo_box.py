"""Compact fields with content-sized, screen-bounded Qt dropdowns."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QListView, QStyle, QWidget


class ReadableComboBox(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        view = QListView()
        view.setTextElideMode(Qt.TextElideMode.ElideNone)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setView(view)
        self.setMaxVisibleItems(12)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)

    def showPopup(self) -> None:
        view = self.view()
        for row in range(self.count()):
            if not self.itemData(row, Qt.ItemDataRole.ToolTipRole):
                self.setItemData(row, self.itemText(row), Qt.ItemDataRole.ToolTipRole)
        view.ensurePolished()
        view.doItemsLayout()
        # Delegate metrics include the active font, icons and stylesheet padding.
        # Qt widget coordinates already use device-independent pixels.
        available = self.screen().availableGeometry()
        frame = 2 * view.frameWidth()
        scrollbar = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        width = max(self.width(), view.sizeHintForColumn(0) + frame + scrollbar + 8)
        view.setMinimumWidth(min(width, max(1, available.width() - 4)))
        super().showPopup()
        # QComboBox resets the popup scroll policy while opening it.
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.doItemsLayout()
        popup = view.window()
        rect = popup.geometry()
        rect.setWidth(min(rect.width(), available.width()))
        rect.moveLeft(max(available.left(), min(rect.left(), available.right() - rect.width() + 1)))
        popup.setGeometry(rect)
