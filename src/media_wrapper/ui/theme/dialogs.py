"""Keep file pickers, notifications and help in the same window design."""
from PySide6.QtCore import QEvent, QFileInfo, QObject, QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
)

from media_wrapper.ui.theme import apply_theme
from media_wrapper.ui.theme.icons import icon
from media_wrapper.ui.theme.tokens import COLORS


class FileIcons(QFileIconProvider):
    def icon(self, entry):
        if isinstance(entry, QFileInfo):
            name = 'folder' if entry.isDir() else 'file'
        else:
            name = {
                QFileIconProvider.IconType.Folder: 'folder',
                QFileIconProvider.IconType.File: 'file',
                QFileIconProvider.IconType.Trashcan: 'trash',
            }.get(entry, 'media')
        return icon(name, color=COLORS['secondary'])


class DialogHeader(QFrame):
    """A dialog caption without default-button or window-state side effects."""
    def __init__(self, dialog: QDialog) -> None:
        super().__init__(dialog)
        self.setObjectName('dialogHeader')
        self.setAccessibleName('Dialog title bar')
        self._drag_offset = None
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 0, 0, 0)
        self.title = QLabel(dialog.windowTitle())
        self.title.setProperty('role', 'sectionTitle')
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.title, 1)
        self.close_button = QPushButton()
        self.close_button.setObjectName('windowClose')
        self.close_button.setProperty('variant', 'windowControl')
        self.close_button.setAutoDefault(False)
        self.close_button.setIcon(icon('close', 14))
        self.close_button.setIconSize(QSize(14, 14))
        self.close_button.setFixedSize(32, 32)
        self.close_button.setAccessibleName('Close dialog')
        self.close_button.setToolTip('Close dialog')
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(dialog.close)
        row.addWidget(self.close_button)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            dialog = self.parentWidget()
            handle = dialog.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
            self._drag_offset = event.globalPosition().toPoint() - dialog.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.parentWidget().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class DialogTheme(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._decorating = False
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
        # ChildPolished runs after a dialog's construction, before it is shown.
        # Local filters avoid observing unrelated widgets and application teardown.
        window.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.ChildPolished and not self._decorating:
            child = event.child()
            if isinstance(child, QDialog) and not child.property('studioDialog'):
                self._decorating = True
                try:
                    self.decorate(child)
                finally:
                    self._decorating = False
        elif (kind in (QEvent.Type.Show, QEvent.Type.Resize, QEvent.Type.WindowTitleChange)
              and isinstance(watched, QDialog)):
            header = watched.findChild(DialogHeader, 'dialogHeader')
            if header is not None:
                header.title.setText(watched.windowTitle())
                header.setGeometry(10, 4, max(0, watched.width() - 20), 36)
                header.raise_()
        return False

    def decorate(self, dialog: QDialog) -> None:
        from media_wrapper.ui.widgets.window_resize import WindowResize

        dialog.setProperty('studioDialog', True)
        dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        apply_theme(dialog)
        # QWidget margins reserve space for the overlay independently of the
        # layout margins rebuilt by QMessageBox when its icon or text changes.
        margins = dialog.contentsMargins()
        dialog.setContentsMargins(margins.left(), margins.top() + 44,
                                  margins.right(), margins.bottom())
        header = DialogHeader(dialog)
        header.title.setObjectName('studioDialogTitle')
        header.resize_handler = WindowResize(dialog)
        dialog.installEventFilter(self)
        header.show()
        if isinstance(dialog, QFileDialog):
            header.file_icons = FileIcons()
            dialog.setIconProvider(header.file_icons)
        if isinstance(dialog, QMessageBox):
            names = {QMessageBox.Icon.Information: ('info', 'accent'),
                     QMessageBox.Icon.Question: ('info', 'accent'),
                     QMessageBox.Icon.Warning: ('warning', 'accent'),
                     QMessageBox.Icon.Critical: ('warning', 'error')}
            if presentation := names.get(dialog.icon()):
                name, color = presentation
                dialog.setIconPixmap(icon(name, 36, COLORS[color]).pixmap(36, 36))
