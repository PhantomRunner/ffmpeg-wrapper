"""Read-only container-time overview; no decoded waveform or invented timing."""
import math

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QListWidget,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from media_wrapper.ui.theme.tokens import COLORS


class MediaTimeline(QWidget):
    stream_selected = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.media = None
        layout = QVBoxLayout(self)
        self.summary = QLabel('Inspect a source to display its stream lanes.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        split = QSplitter()
        self.lanes = QListWidget()
        self.lanes.setAccessibleName('Source stream lanes; read-only timing')
        self.lanes.currentRowChanged.connect(self.select_lane)
        split.addWidget(self.lanes)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setAccessibleName('Source container time ruler; stream timing is not individually probed')
        split.addWidget(self.view)
        split.setSizes([250, 750])
        layout.addWidget(split)
        self.scene.selectionChanged.connect(self.select_graphics_lane)

    def set_media(self, media) -> None:
        if media is self.media:
            return
        self.media = media
        self.lanes.clear()
        self.scene.clear()
        if media is None:
            self.summary.setText('Inspect a source to display its stream lanes.')
            return
        duration = media.duration
        known = duration is not None and math.isfinite(duration) and duration > 0
        self.summary.setText(f'{media.path.name} · ' + (f'{duration:g} s container duration' if known else 'Duration unknown') +
                             ' · Read-only overview; lane widths use container duration, not individual stream start/end times.')
        if known:
            for tick in range(6):
                x = tick * 160
                label = self.scene.addText(f'{duration * tick / 5:.2f} s')
                label.setDefaultTextColor(QColor(COLORS['text']))
                label.setPos(x, 0)
                self.scene.addLine(x, 25, x, 30 + 36 * len(media.streams), QPen(QColor(COLORS['border'])))
        for row, stream in enumerate(media.streams):
            text = f'{stream.index}: {stream.kind} · {stream.codec} · {stream.language or "language unknown"}'
            self.lanes.addItem(text)
            if known:
                lane = self.scene.addRect(0, 32 + row * 36, 800, 26, QPen(QColor(COLORS['border'])), QColor(COLORS['control']))
                lane.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                lane.setData(0, row)
                lane.setToolTip(text + '\nContainer span only; stream timestamps unavailable.')
                label = self.scene.addText(text)
                label.setDefaultTextColor(QColor(COLORS['text']))
                label.setPos(4, 31 + row * 36)
        if not known:
            item = self.scene.addText('Duration unknown — no time scale can be drawn.\nStream metadata remains available in the lane list.')
            item.setDefaultTextColor(QColor(COLORS['text']))
        self.scene.setSceneRect(self.scene.itemsBoundingRect())

    def select_lane(self, row: int) -> None:
        if self.media and 0 <= row < len(self.media.streams):
            self.stream_selected.emit(self.media.streams[row])

    def select_graphics_lane(self) -> None:
        items = self.scene.selectedItems()
        if items:
            self.lanes.setCurrentRow(items[0].data(0))
