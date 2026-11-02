"""Resizable workspace composition and independently versioned layout preferences."""
from PySide6.QtCore import QByteArray, QEvent, QPoint, QSettings, QSize, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.ui.panels.playback import PlaybackPanel
from media_wrapper.ui.theme.icons import icon
from media_wrapper.ui.theme.tokens import COLORS
from media_wrapper.ui.widgets.controls import ActionButton, PanelHeader


class WindowHeader(QFrame):
    """Compact application chrome with the platform's own window dragging."""

    def __init__(self, window: QWidget) -> None:
        super().__init__()
        self._window = window
        self._drag_offset: QPoint | None = None
        self.setObjectName('appHeader')
        self.setAccessibleName('Application title bar')
        self.controls = QWidget()
        self.controls.setObjectName('windowControls')
        controls_layout = QHBoxLayout(self.controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)
        self.minimize_button = self._control('minimize', 'Minimize window')
        self.maximize_button = self._control('maximize', 'Maximize window')
        self.close_button = self._control('close', 'Close window')
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)
        for control in (self.minimize_button, self.maximize_button, self.close_button):
            controls_layout.addWidget(control)
        window.installEventFilter(self)

    def _control(self, name: str, label: str) -> ActionButton:
        button = ActionButton('')
        button.setObjectName('window' + name.title())
        button.setProperty('variant', 'windowControl')
        button.setIcon(icon(name, 14))
        button.setIconSize(QSize(14, 14))
        button.setFixedSize(32, 32)
        button.setAccessibleName(label)
        button.setToolTip(label)
        return button

    def toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def eventFilter(self, watched, event) -> bool:
        if watched is self._window and event.type() == QEvent.Type.WindowStateChange:
            maximized = self._window.isMaximized()
            self.maximize_button.setIcon(icon('restore' if maximized else 'maximize', 14))
            label = 'Restore window' if maximized else 'Maximize window'
            self.maximize_button.setAccessibleName(label)
            self.maximize_button.setToolTip(label)
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            handle = self._window.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
            if not self._window.isMaximized():
                self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


def scroll_panel(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setProperty('role', 'panelScroll')
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setMinimumWidth(160)
    return area


def framed_panel(widget: QWidget) -> QFrame:
    panel = QFrame()
    panel.setProperty('role', 'workspacePanel')
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)
    layout.addWidget(widget)
    return panel


class Workspace(QWidget):
    def __init__(self, window, settings: QSettings | None = None) -> None:
        super().__init__()
        self.window = window
        self.settings = settings
        self.mode = -1
        self._layouts: dict[int, tuple[QByteArray, QByteArray]] = {}
        self._preview_choices: dict[int, bool] = {}
        self.setObjectName('mediaWorkspace')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        header = WindowHeader(window)
        self.title_bar = header
        toolbar = QHBoxLayout(header)
        toolbar.setContentsMargins(4, 4, 4, 4)
        toolbar.setSpacing(12)
        brand = QLabel()
        brand.setObjectName('brandMark')
        brand.setFixedSize(40, 40)
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setPixmap(icon('media', 24).pixmap(24, 24))
        brand.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        toolbar.addWidget(brand)
        identity = QVBoxLayout()
        identity.setSpacing(1)
        title = QLabel('Media Wrapper')
        title.setObjectName('brandTitle')
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        subtitle = QLabel('FFmpeg workspace')
        subtitle.setObjectName('brandSubtitle')
        subtitle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        identity.addWidget(title)
        identity.addWidget(subtitle)
        toolbar.addLayout(identity)
        toolbar.addStretch()
        self.preview_toggle = ActionButton('Preview')
        self.preview_toggle.setCheckable(True)
        self.preview_toggle.setProperty('variant', 'ghost')
        self.preview_toggle.setIcon(icon('video'))
        self.preview_toggle.setAccessibleName('Show source preview')
        self.preview_toggle.setToolTip('Show or hide the source preview')
        self.preview_toggle.toggled.connect(self.toggle_preview)
        toolbar.addWidget(self.preview_toggle)
        reset = ActionButton('Reset layout')
        reset.setObjectName('resetLayout')
        reset.setProperty('variant', 'ghost')
        reset.setIcon(icon('reset'))
        reset.clicked.connect(self.reset_layout)
        toolbar.addWidget(reset)
        self.import_button = ActionButton('Import media', primary=True)
        self.import_button.setIcon(icon('import', color=COLORS['on_accent']))
        self.import_button.clicked.connect(window.choose_file)
        toolbar.addWidget(self.import_button)
        toolbar.addSpacing(8)
        toolbar.addWidget(header.controls)
        layout.addWidget(header)
        navigation_bar = QFrame()
        navigation_bar.setObjectName('navigationBar')
        navigation_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        navigation_layout = QHBoxLayout(navigation_bar)
        navigation_layout.setContentsMargins(4, 3, 12, 3)
        navigation_layout.setSpacing(12)
        window.navigation.setFlow(window.navigation.Flow.LeftToRight)
        window.navigation.setWrapping(False)
        window.navigation.setSpacing(3)
        window.navigation.setGridSize(QSize(120, 38))
        window.navigation.setIconSize(QSize(16, 16))
        window.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        window.navigation.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for row, name in enumerate(('inspect', 'remux', 'convert', 'compress', 'queue', 'settings')):
            item = window.navigation.item(row)
            item.setSizeHint(QSize(116, 36))
            item.setIcon(icon(name))
            item.setToolTip(f'{item.text()} (Alt+{row + 1})')
        window.navigation.setMaximumWidth(16777215)
        window.navigation.setFixedHeight(44)
        navigation_layout.addWidget(window.navigation, 1)
        mode_hint = QLabel('ALT 1–6')
        mode_hint.setObjectName('modeHint')
        mode_hint.setToolTip('Switch workspace with Alt+1 through Alt+6')
        navigation_layout.addWidget(mode_hint)
        layout.addWidget(navigation_bar)
        self.horizontal = QSplitter(Qt.Orientation.Horizontal)
        self.horizontal.setObjectName('workspaceSplit')
        self.horizontal.setChildrenCollapsible(False)
        self.horizontal.setHandleWidth(12)
        self.library = framed_panel(scroll_panel(window.files_view))
        self.horizontal.addWidget(self.library)
        self.preview = QFrame()
        self.preview.setObjectName('sourcePreviewPanel')
        self.preview.setProperty('role', 'workspacePanel')
        preview_layout = QHBoxLayout(self.preview)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(18)
        details = QVBoxLayout()
        details.setSpacing(6)
        details.addWidget(PanelHeader('Source preview'))
        self.source = QLabel('No source selected')
        self.source.setObjectName('sourcePath')
        self.source.setProperty('role', 'secondary')
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        self.source.setWordWrap(True)
        details.addWidget(self.source)
        self.playback = PlaybackPanel()
        preview_layout.addWidget(self.playback, 2)
        self.feedback = QTabWidget()
        self.feedback.setObjectName('previewFeedback')
        window.output.setProperty('role', 'console')
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
        layout.addWidget(self.vertical, 1)
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
        self.update_preview_visibility()
        self.default_layout()
        if mode in self._layouts:
            horizontal, vertical = self._layouts[mode]
            restored = self.horizontal.restoreState(horizontal) and self.vertical.restoreState(vertical)
            if not restored or any(size <= 0 and not self.horizontal.widget(i).isHidden()
                                   for i, size in enumerate(self.horizontal.sizes())) or any(
                    size <= 0 and not self.vertical.widget(i).isHidden()
                    for i, size in enumerate(self.vertical.sizes())):
                self.default_layout()

    def update_preview_visibility(self) -> None:
        available = self.mode in (0, 2, 3)
        visible = available and self._preview_choices.get(
            self.mode, self.mode == 0 or self.window.height() >= 700)
        self.preview_toggle.setVisible(available)
        self.preview_toggle.blockSignals(True)
        self.preview_toggle.setChecked(visible)
        self.preview_toggle.blockSignals(False)
        self.preview.setVisible(visible)

    def toggle_preview(self, visible: bool) -> None:
        if self.mode < 0:
            return
        self._preview_choices[self.mode] = visible
        self.update_preview_visibility()
        if visible:
            self.default_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'preview') and self.mode >= 0:
            self.update_preview_visibility()

    def default_layout(self) -> None:
        proportions = {0: [280, 720], 1: [280, 720],
                       2: [280, 720], 3: [280, 720],
                       4: [0, 1000], 5: [0, 1000]}
        self.horizontal.setSizes(proportions[self.mode])
        self.vertical.setSizes([190, max(300, self.height() - 190)])

    def reset_layout(self) -> None:
        self._layouts.pop(self.mode, None)
        self._preview_choices.pop(self.mode, None)
        self.update_preview_visibility()
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
    panel.setObjectName('operationPanel')
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    layout.addWidget(view, 1)
    footer = QFrame()
    footer.setObjectName('operationActions')
    footer_layout = QVBoxLayout(footer)
    footer_layout.setContentsMargins(10, 10, 10, 10)
    footer_layout.setSpacing(8)
    view.enqueue_button.setProperty('variant', 'primary')
    view.run_button.setProperty('variant', 'secondary')
    view.enqueue_button.setIcon(icon('queue', color=COLORS['on_accent']))
    view.preview_button.setIcon(icon('inspect'))
    view.run_button.setIcon(icon('convert'))
    footer_layout.addWidget(view.enqueue_button)
    actions = QHBoxLayout()
    actions.setSpacing(8)
    actions.addWidget(view.preview_button)
    actions.addWidget(view.run_button)
    footer_layout.addLayout(actions)
    if remux:
        footer_layout.addWidget(view.cancel_button)
        footer_layout.addWidget(view.progress_label)
    layout.addWidget(footer)
    return panel
