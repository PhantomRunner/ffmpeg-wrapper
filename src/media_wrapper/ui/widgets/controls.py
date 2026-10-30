"""Accessible, behavior-free workstation controls; no application services."""
from typing import ClassVar

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.ui.theme.icons import icon
from media_wrapper.ui.theme.tokens import COLORS, PADDING, SPACING


class PanelHeader(QWidget):
    def __init__(self, title: str, description: str = '', parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty('role', 'panelHeader')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, SPACING)
        layout.setSpacing(5)
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
    ICONS: ClassVar[tuple[tuple[tuple[str, ...], str], ...]] = (
        (('cancel',), 'close'),
        (('add to queue', 'queue selected'), 'queue'),
        (('retry', 'scan', 'detect'), 'refresh'),
        (('reset layout',), 'layout'),
        (('add files',), 'plus'),
        (('import', 'load queue'), 'upload'),
        (('export', 'save'), 'download'),
        (('browse', 'choose output', 'open output', 'select bundled'), 'folder'),
        (('inspect',), 'search'),
        (('clear',), 'trash'),
        (('validate', 'apply'), 'check'),
        (('run', 'start', 'play'), 'play'),
    )

    def __init__(self, text: str, parent: QWidget | None = None, *, primary: bool = False) -> None:
        super().__init__(text, parent)
        self._icon_name = next((name for prefixes, name in self.ICONS
                                if text.lower().startswith(prefixes)), '')
        self.setProperty('variant', 'primary' if primary else 'secondary')
        self.setAccessibleName(text.replace('…', ''))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(16, 16))
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        if self._icon_name:
            foreground = COLORS['on_accent'] if self.property('variant') == 'primary' else COLORS['text']
            self.setIcon(icon(self._icon_name, color=foreground))

    def event(self, event: QEvent) -> bool:
        result = super().event(event)
        if (event.type() == QEvent.Type.DynamicPropertyChange
                and event.propertyName() == b'variant' and hasattr(self, '_icon_name')):
            self._refresh_icon()
        return result


class StatusChip(QLabel):
    SYMBOLS: ClassVar[dict[str, str]] = {'neutral': '●', 'success': '✓', 'error': '!', 'loading': '●'}

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
        layout.setContentsMargins(PADDING * 2, PADDING * 2, PADDING * 2, PADDING * 2)
        layout.setSpacing(SPACING)
        illustration = QLabel()
        illustration.setProperty('role', 'emptyIcon')
        illustration.setPixmap(icon('upload', size=28, color=COLORS['secondary']).pixmap(28, 28))
        illustration.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading = QLabel(title)
        heading.setProperty('role', 'emptyTitle')
        heading.setWordWrap(True)
        body = QLabel(description)
        body.setProperty('role', 'secondary')
        body.setWordWrap(True)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(illustration)
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)


class FieldRow(QWidget):
    def __init__(self, title: str, field: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING)
        self.label = QLabel(title)
        self.label.setProperty('role', 'fieldLabel')
        self.label.setBuddy(field)
        self.label.setWordWrap(True)
        field.setAccessibleName(title.replace('&', ''))
        layout.addWidget(self.label)
        layout.addWidget(field, 1)
