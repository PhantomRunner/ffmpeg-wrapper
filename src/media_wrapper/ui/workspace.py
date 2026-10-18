"""Resizable workspace composition and independently versioned layout preferences."""
from PySide6.QtCore import QByteArray, QSettings, QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.ui.panels.playback import PlaybackPanel
from media_wrapper.ui.widgets.controls import ActionButton, PanelHeader


def scroll_panel(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setMinimumWidth(160)
    return area


def framed_panel(widget: QWidget) -> QFrame:
    panel = QFrame()
    panel.setProperty('role', 'workspacePanel')
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.addWidget(widget)
    return panel


class Workspace(QWidget):
    def __init__(self, window, settings: QSettings | None = None) -> None:
        super().__init__()
        self.window = window
        self.settings = settings
        self.mode = -1
        self._layouts: dict[int, tuple[QByteArray, QByteArray]] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel('MEDIA WORKSTATION'))
        toolbar.addStretch()
        self.import_button = ActionButton('Import media…', primary=True)
        self.import_button.clicked.connect(window.choose_file)
        toolbar.addWidget(self.import_button)
        reset = ActionButton('Reset layout')
        reset.clicked.connect(self.reset_layout)
        toolbar.addWidget(reset)
        layout.addLayout(toolbar)
        window.navigation.setFlow(window.navigation.Flow.LeftToRight)
        window.navigation.setWrapping(False)
        window.navigation.setGridSize(QSize(96, 32))
        for row in range(window.navigation.count()):
            window.navigation.item(row).setSizeHint(QSize(92, 28))
        window.navigation.setMaximumWidth(16777215)
        window.navigation.setFixedHeight(36)
        layout.addWidget(window.navigation)
        self.horizontal = QSplitter(Qt.Orientation.Horizontal)
        self.horizontal.setObjectName('workspaceSplit')
        self.horizontal.setChildrenCollapsible(False)
        self.horizontal.setHandleWidth(12)
        self.library = framed_panel(scroll_panel(window.files_view))
        self.horizontal.addWidget(self.library)
        self.preview = QFrame()
        self.preview.setProperty('role', 'workspacePanel')
        preview_layout = QHBoxLayout(self.preview)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(6)
        details = QVBoxLayout()
        details.addWidget(PanelHeader('Source Preview'))
        self.source = QLabel('No source selected')
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        self.source.setWordWrap(True)
        details.addWidget(self.source)
        self.playback = PlaybackPanel()
        preview_layout.addWidget(self.playback, 2)
        self.feedback = QTabWidget()
        self.feedback.addTab(window.output, 'Operation feedback')
        details.addWidget(self.feedback, 1)
        preview_layout.addLayout(details, 3)
        window.pages.setMinimumWidth(200)
        self.inspector = framed_panel(window.pages)
        self.horizontal.addWidget(self.inspector)
        self.vertical = QSplitter(Qt.Orientation.Vertical)
        self.vertical.setObjectName('previewSplit')
        self.vertical.setChildrenCollapsible(False)
        self.vertical.setHandleWidth(12)
        self.vertical.addWidget(self.preview)
        self.vertical.addWidget(self.horizontal)
        layout.addWidget(self.vertical)
        window.navigation.currentRowChanged.connect(self.set_mode)
        self.set_mode(window.navigation.currentRow())
        self.restore_layout()

    def remember_layout(self) -> None:
        if self.mode >= 0:
            self._layouts[self.mode] = (self.horizontal.saveState(), self.vertical.saveState())

    def set_mode(self, mode: int) -> None:
        if not 0 <= mode < 6 or mode == self.mode:
            return
        self.remember_layout()
        self.mode = mode
        self.library.setVisible(mode < 4)
        self.preview.setVisible(mode in (0, 2, 3))
        self.default_layout()
        if mode in self._layouts:
            horizontal, vertical = self._layouts[mode]
            restored = self.horizontal.restoreState(horizontal) and self.vertical.restoreState(vertical)
            if not restored or any(size <= 0 and not self.horizontal.widget(i).isHidden()
                                   for i, size in enumerate(self.horizontal.sizes())) or any(
                    size <= 0 and not self.vertical.widget(i).isHidden()
                    for i, size in enumerate(self.vertical.sizes())):
                self.default_layout()

    def default_layout(self) -> None:
        proportions = {0: [280, 720], 1: [280, 720],
                       2: [280, 720], 3: [280, 720],
                       4: [0, 1000], 5: [0, 1000]}
        self.horizontal.setSizes(proportions[self.mode])
        self.vertical.setSizes([190, max(300, self.height() - 190)])

    def reset_layout(self) -> None:
        self._layouts.pop(self.mode, None)
        self.default_layout()

    def restore_layout(self) -> None:
        if self.settings is None:
            return
        version = str(self.settings.value('workspace/version', ''))
        if version not in ('1', '2', '3', '4'):
            return
        try:
            mode = int(self.settings.value('workspace/mode', 0))
        except (ValueError, TypeError):
            mode = 0
        mode = mode if 0 <= mode < 6 else 0
        # Old three-column geometry is incompatible; preserve only the selected mode.
        if version == '4':
            for index in range(6):
                prefix = f'workspace/modes/{index}/'
                horizontal = self.settings.value(prefix + 'horizontal')
                vertical = self.settings.value(prefix + 'vertical')
                if isinstance(horizontal, QByteArray) and isinstance(vertical, QByteArray):
                    self._layouts[index] = (horizontal, vertical)
        # Do not overwrite the restored initial mode with the startup geometry.
        self.mode = -1
        self.window.navigation.setCurrentRow(mode)
        self.set_mode(mode)

    def save_layout(self) -> None:
        if self.settings is None:
            return
        self.remember_layout()
        self.settings.setValue('workspace/version', '4')
        self.settings.remove('workspace/modes')
        for mode, (horizontal, vertical) in self._layouts.items():
            prefix = f'workspace/modes/{mode}/'
            self.settings.setValue(prefix + 'horizontal', horizontal)
            self.settings.setValue(prefix + 'vertical', vertical)
            self.settings.remove(prefix + 'timeline')
        self.settings.remove('workspace/vertical')
        self.settings.remove('workspace/timeline')
        self.settings.setValue('workspace/mode', self.mode)
        self.settings.sync()


def operation_panel(view: QWidget, *, remux: bool = False) -> QWidget:
    """Keep operation actions reachable while long configuration forms scroll."""
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view, 1)
    view.enqueue_button.setProperty('variant', 'primary')
    view.run_button.setProperty('variant', 'secondary')
    layout.addWidget(view.enqueue_button)
    actions = QHBoxLayout()
    actions.addWidget(view.preview_button)
    actions.addWidget(view.run_button)
    layout.addLayout(actions)
    if remux:
        layout.addWidget(view.cancel_button)
        layout.addWidget(view.progress_label)
    return panel
