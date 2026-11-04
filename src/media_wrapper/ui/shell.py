"""Native-window, three-page shell. Pages own their contextual actions."""
from PySide6.QtCore import QByteArray, QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.domain.operations import MediaOperation
from media_wrapper.ui.widgets.controls import ActionButton


class WorkspaceToolbar(QFrame):
    operation_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('workspaceToolbar')
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 8)
        self.add_files = ActionButton('Add files')
        self.add_folder = ActionButton('Add folder')
        self.remove = ActionButton('Remove')
        for button in (self.add_files, self.add_folder, self.remove):
            row.addWidget(button)
        row.addStretch()
        self.operations = QButtonGroup(self)
        self.operation_buttons = {}
        for operation in (MediaOperation.REMUX, MediaOperation.COMPRESS, MediaOperation.CONVERT):
            button = ActionButton(operation.value.title())
            button.setCheckable(True)
            self.operations.addButton(button)
            self.operation_buttons[operation] = button
            button.clicked.connect(lambda _checked=False, operation=operation:
                                   self.operation_changed.emit(operation))
            row.addWidget(button)
        self.operation_buttons[MediaOperation.REMUX].setChecked(True)

    def set_operation(self, operation):
        self.operation_buttons[operation].setChecked(True)


class AppShell(QWidget):
    page_changed = Signal(str)
    ROUTES = ('workspace', 'queue', 'settings')

    def __init__(self, workspace, queue, settings, parent=None):
        super().__init__(parent)
        self.setObjectName('workspaceRoot')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel('FFmpeg Wrapper')
        title.setObjectName('brandTitle')
        header.addWidget(title)
        header.addSpacing(24)
        self.navigation = QButtonGroup(self)
        self.buttons = {}
        for route in self.ROUTES:
            if route == 'settings':
                header.addStretch()
            button = ActionButton(route.title())
            button.setCheckable(True)
            button.setAccessibleName(f'Open {route.title()}')
            self.navigation.addButton(button)
            self.buttons[route] = button
            header.addWidget(button)
            button.clicked.connect(lambda _checked=False, route=route: self.set_page(route))
        layout.addLayout(header)
        self.stack = QStackedWidget()
        for page in (workspace, queue, settings):
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)
        self.set_page('workspace')

    @property
    def page(self):
        return self.ROUTES[self.stack.currentIndex()]

    def set_page(self, route):
        if route not in self.ROUTES:
            route = 'workspace'
        self.stack.setCurrentIndex(self.ROUTES.index(route))
        self.buttons[route].setChecked(True)
        self.page_changed.emit(route)


class WorkspaceLayout:
    """Only splitter geometry lives in QSettings; routes stay with preferences."""
    VERSION = '5'

    def __init__(self, splitter: QSplitter, settings: QSettings | None):
        self.splitter, self.settings = splitter, settings
        splitter.setChildrenCollapsible(False)
        splitter.setOrientation(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)

    def restore(self):
        self.splitter.setSizes([640, 360])
        if self.settings and str(self.settings.value('flat/version', '')) == self.VERSION:
            saved = self.settings.value('flat/splitter')
            if isinstance(saved, QByteArray) and (not self.splitter.restoreState(saved)
                                                  or any(n <= 0 for n in self.splitter.sizes())):
                self.splitter.setSizes([640, 360])

    def save(self):
        if self.settings:
            self.settings.setValue('flat/version', self.VERSION)
            self.settings.setValue('flat/splitter', self.splitter.saveState())
            self.settings.sync()

    @staticmethod
    def legacy_route(page: int):
        return ('queue' if page == 4 else 'settings' if page == 5 else 'workspace',
                {2: MediaOperation.CONVERT, 3: MediaOperation.COMPRESS}.get(page, MediaOperation.REMUX))
