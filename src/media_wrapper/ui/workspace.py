"""Resizable workspace composition and independently versioned layout preferences."""
from PySide6.QtCore import QByteArray, QSettings, QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.ui.panels.media_timeline import MediaTimeline
from media_wrapper.ui.panels.playback import PlaybackPanel
from media_wrapper.ui.widgets.controls import ActionButton, PanelHeader


def scroll_panel(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setMinimumWidth(160)
    return area


class Workspace(QWidget):
    def __init__(self, window, settings: QSettings | None = None) -> None:
        super().__init__()
        self.window = window
        self.settings = settings
        self.mode = -1
        self._layouts: dict[int, tuple[QByteArray, QByteArray, int]] = {}
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
        settings_button = ActionButton('Settings')
        settings_button.clicked.connect(lambda: window.navigation.setCurrentRow(5))
        toolbar.addWidget(settings_button)
        layout.addLayout(toolbar)
        window.navigation.setFlow(window.navigation.Flow.LeftToRight)
        window.navigation.setWrapping(False)
        window.navigation.setGridSize(QSize(112, 40))
        for row in range(window.navigation.count()):
            window.navigation.item(row).setSizeHint(QSize(108, 36))
        window.navigation.setMaximumWidth(16777215)
        window.navigation.setFixedHeight(44)
        layout.addWidget(window.navigation)
        self.vertical = QSplitter(Qt.Orientation.Vertical)
        self.horizontal = QSplitter(Qt.Orientation.Horizontal)
        for splitter in (self.vertical, self.horizontal):
            splitter.setChildrenCollapsible(False)
            splitter.setHandleWidth(6)
        self.library = scroll_panel(window.files_view)
        self.horizontal.addWidget(self.library)
        self.preview = QWidget()
        preview_layout = QVBoxLayout(self.preview)
        preview_layout.addWidget(PanelHeader('Source Preview', 'Selected source and operation feedback'))
        self.source = QLabel('No source selected')
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        self.source.setWordWrap(True)
        preview_layout.addWidget(self.source)
        self.playback = PlaybackPanel()
        preview_layout.addWidget(self.playback, 2)
        self.feedback = QTabWidget()
        self.feedback.addTab(window.output, 'Operation feedback')
        preview_layout.addWidget(self.feedback, 1)
        self.horizontal.addWidget(self.preview)
        window.pages.setMinimumWidth(200)
        self.horizontal.addWidget(window.pages)
        self.vertical.addWidget(self.horizontal)
        self.timelines = QTabWidget()
        self.timelines.addTab(scroll_panel(window.queue_view), 'Processing Timeline')
        self.media_timeline = MediaTimeline()
        self.timelines.addTab(self.media_timeline, 'Media Timeline')
        self.media_timeline.stream_selected.connect(self.show_stream)
        if self.playback.service:
            self.playback.service.position_changed.connect(self.media_timeline.set_position)
            self.media_timeline.seek_requested.connect(self.playback.service.seek)
        self.vertical.addWidget(self.timelines)
        layout.addWidget(self.vertical)
        window.navigation.currentRowChanged.connect(self.set_mode)
        self.set_mode(window.navigation.currentRow())
        self.restore_layout()

    def show_stream(self, stream) -> None:
        from media_wrapper.ui.inspection_presenter import stream_values
        self.window.navigation.setCurrentRow(0)
        self.window.output.setPlainText('Selected source stream (selection does not change export choices):\n' +
                                       ' | '.join(stream_values(stream)))

    def remember_layout(self) -> None:
        if self.mode >= 0:
            self._layouts[self.mode] = (self.horizontal.saveState(), self.vertical.saveState(),
                                        self.timelines.currentIndex())

    def set_mode(self, mode: int) -> None:
        if not 0 <= mode < 6 or mode == self.mode:
            return
        self.remember_layout()
        self.mode = mode
        self.horizontal.setVisible(mode != 4)
        self.library.setVisible(mode < 4)
        self.preview.setVisible(mode in (0, 2, 3))
        self.window.pages.setVisible(mode != 4)
        self.timelines.setVisible(mode != 5)
        self.timelines.setTabVisible(1, mode != 4)
        self.default_layout()
        if mode in self._layouts:
            horizontal, vertical, timeline = self._layouts[mode]
            self.horizontal.restoreState(horizontal)
            self.vertical.restoreState(vertical)
            self.timelines.setCurrentIndex(0 if mode == 4 else timeline)

    def default_layout(self) -> None:
        proportions = {0: [230, 500, 320], 1: [280, 0, 720],
                       2: [220, 330, 500], 3: [220, 300, 530],
                       4: [230, 470, 300], 5: [0, 0, 1000]}
        self.horizontal.setSizes(proportions[self.mode])
        self.vertical.setSizes([650, 350] if self.mode == 0 else [760, 240])
        self.timelines.setCurrentIndex(1 if self.mode == 0 else 0)

    def reset_layout(self) -> None:
        self._layouts.pop(self.mode, None)
        self.default_layout()

    def restore_layout(self) -> None:
        if self.settings is None:
            return
        version = str(self.settings.value('workspace/version', ''))
        if version not in ('1', '2'):
            return
        try:
            mode = int(self.settings.value('workspace/mode', 0))
        except (ValueError, TypeError):
            mode = 0
        mode = mode if 0 <= mode < 6 else 0
        for index in (range(6) if version == '2' else [mode]):
            prefix = f'workspace/modes/{index}/' if version == '2' else 'workspace/'
            horizontal = self.settings.value(prefix + 'horizontal')
            vertical = self.settings.value(prefix + 'vertical')
            try:
                timeline = int(self.settings.value(prefix + 'timeline', 0))
            except (ValueError, TypeError):
                timeline = 0
            if isinstance(horizontal, QByteArray) and isinstance(vertical, QByteArray):
                self._layouts[index] = (horizontal, vertical, timeline if timeline in (0, 1) else 0)
        # Do not overwrite the restored initial mode with the startup geometry.
        self.mode = -1
        self.window.navigation.setCurrentRow(mode)
        self.set_mode(mode)

    def save_layout(self) -> None:
        if self.settings is None:
            return
        self.remember_layout()
        self.settings.setValue('workspace/version', '2')
        for mode, (horizontal, vertical, timeline) in self._layouts.items():
            prefix = f'workspace/modes/{mode}/'
            self.settings.setValue(prefix + 'horizontal', horizontal)
            self.settings.setValue(prefix + 'vertical', vertical)
            self.settings.setValue(prefix + 'timeline', timeline)
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
