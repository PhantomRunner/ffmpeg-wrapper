"""Accessible, behavior-free workstation controls; no application services."""
from typing import ClassVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.ui.theme.tokens import PADDING, SPACING


class PanelHeader(QWidget):
    def __init__(self, title: str, description: str = '', parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty('role', 'panelHeader')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, SPACING)
        layout.setSpacing(2)
        self.title = QLabel(title)
        self.title.setProperty('role', 'panelTitle')
        self.title.setWordWrap(True)
        self.description = QLabel(description)
        self.description.setProperty('role', 'secondary')
        self.description.setWordWrap(True)
        self.description.setVisible(bool(description))
        layout.addWidget(self.title)
        layout.addWidget(self.description)
        self.setAccessibleName(title)


class ActionButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None, *, primary: bool = False) -> None:
        super().__init__(text, parent)
        self.setProperty('variant', 'primary' if primary else 'secondary')
        self.setAccessibleName(text.replace('…', ''))
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class StatusChip(QLabel):
    SYMBOLS: ClassVar[dict[str, str]] = {'neutral': '○', 'success': '✓', 'error': '!', 'loading': '…'}

    def __init__(self, text: str = 'Ready', state: str = 'neutral', parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty('role', 'statusChip')
        self.set_status(text, state)

    def set_status(self, text: str, state: str = 'neutral') -> None:
        if state not in self.SYMBOLS:
            raise ValueError('Unsupported status presentation')
        if self.property('state') == state and self.accessibleName() == text:
            return
        self.setProperty('state', state)
        self.setText(f'{self.SYMBOLS[state]}  {text}')
        self.setAccessibleName(text)
        self.setToolTip(text)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class EmptyState(QFrame):
    def __init__(self, title: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty('role', 'emptyState')
        self.setAccessibleName(title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        layout.setSpacing(SPACING)
        heading = QLabel(title)
        heading.setProperty('role', 'emptyTitle')
        heading.setWordWrap(True)
        body = QLabel(description)
        body.setProperty('role', 'secondary')
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)


class FieldRow(QWidget):
    def __init__(self, title: str, field: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING)
        self.label = QLabel(title)
        self.label.setBuddy(field)
        self.label.setWordWrap(True)
        field.setAccessibleName(title.replace('&', ''))
        layout.addWidget(self.label)
        layout.addWidget(field, 1)
