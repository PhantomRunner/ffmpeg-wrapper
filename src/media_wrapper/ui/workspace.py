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

from media_wrapper.ui.widgets.controls import ActionButton, EmptyState, PanelHeader


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
        self.horizontal.addWidget(scroll_panel(window.files_view))
        self.preview = QWidget()
        preview_layout = QVBoxLayout(self.preview)
        preview_layout.addWidget(PanelHeader('Source Preview', 'Selected source and operation feedback'))
        self.source = QLabel('No source selected')
        self.source.setWordWrap(True)
        preview_layout.addWidget(self.source)
        self.fallback = EmptyState('Playback unavailable', 'This workspace currently provides metadata inspection. Processing remains available; no decoded video or audio preview is shown.')
        preview_layout.addWidget(self.fallback, 1)
        self.feedback = QTabWidget()
        self.feedback.addTab(window.output, 'Operation feedback')
        preview_layout.addWidget(self.feedback, 1)
        self.horizontal.addWidget(self.preview)
        window.pages.setMinimumWidth(200)
        self.horizontal.addWidget(window.pages)
        self.vertical.addWidget(self.horizontal)
        self.timelines = QTabWidget()
        self.timelines.addTab(scroll_panel(window.queue_view), 'Processing Timeline')
        self.media_placeholder = EmptyState('Media Timeline', 'Read-only source stream lanes will be available in the timeline phase.')
        self.timelines.addTab(self.media_placeholder, 'Media Timeline')
        self.vertical.addWidget(self.timelines)
        layout.addWidget(self.vertical)
        self.reset_layout()
        self.restore_layout()

    def reset_layout(self) -> None:
        self.horizontal.setSizes([230, 470, 300])
        self.vertical.setSizes([680, 320])
        self.timelines.setCurrentIndex(0)

    def restore_layout(self) -> None:
        if self.settings is None or self.settings.value('workspace/version') != '1':
            return
        for key, splitter in (('horizontal', self.horizontal), ('vertical', self.vertical)):
            value = self.settings.value('workspace/' + key)
            if isinstance(value, QByteArray) and (not splitter.restoreState(value) or any(size <= 0 for size in splitter.sizes())):
                splitter.setSizes([230, 470, 300] if key == 'horizontal' else [680, 320])
        try:
            mode = int(self.settings.value('workspace/mode', 0))
            timeline = int(self.settings.value('workspace/timeline', 0))
        except (ValueError, TypeError):
            mode, timeline = 0, 0
        self.window.navigation.setCurrentRow(mode if 0 <= mode < 6 else 0)
        self.timelines.setCurrentIndex(timeline if timeline in (0, 1) else 0)

    def save_layout(self) -> None:
        if self.settings is None:
            return
        self.settings.setValue('workspace/version', '1')
        self.settings.setValue('workspace/horizontal', self.horizontal.saveState())
        self.settings.setValue('workspace/vertical', self.vertical.saveState())
        self.settings.setValue('workspace/mode', self.window.navigation.currentRow())
        self.settings.setValue('workspace/timeline', self.timelines.currentIndex())
        self.settings.sync()
