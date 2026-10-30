"""Edge resizing for the custom title bar, including window-manager fallback."""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QMainWindow, QWidget


class WindowResize(QObject):
    MARGIN = 6

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.window = window
        self._drag = None
        surfaces = [window]
        if isinstance(window, QMainWindow):
            surfaces.extend((window.centralWidget(), window.statusBar()))
        for surface in surfaces:
            surface.setMouseTracking(True)
            surface.installEventFilter(self)

    def edges_at(self, point):
        edges = Qt.Edge(0)
        if self.window.isMaximized() or self.window.isFullScreen():
            return edges
        if point.x() < self.MARGIN:
            edges |= Qt.Edge.LeftEdge
        elif point.x() >= self.window.width() - self.MARGIN:
            edges |= Qt.Edge.RightEdge
        if point.y() < self.MARGIN:
            edges |= Qt.Edge.TopEdge
        elif point.y() >= self.window.height() - self.MARGIN:
            edges |= Qt.Edge.BottomEdge
        return edges

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.MouseButtonRelease:
            self._drag = None
        elif kind in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
            if self._drag and kind == QEvent.Type.MouseMove:
                edges, origin, initial = self._drag
                delta = event.globalPosition().toPoint() - origin
                rect = initial.adjusted(0, 0, 0, 0)
                minimum = self.window.minimumSize()
                if edges & Qt.Edge.LeftEdge:
                    rect.setLeft(min(initial.left() + delta.x(), initial.right() - minimum.width() + 1))
                if edges & Qt.Edge.RightEdge:
                    rect.setRight(max(initial.right() + delta.x(), initial.left() + minimum.width() - 1))
                if edges & Qt.Edge.TopEdge:
                    rect.setTop(min(initial.top() + delta.y(), initial.bottom() - minimum.height() + 1))
                if edges & Qt.Edge.BottomEdge:
                    rect.setBottom(max(initial.bottom() + delta.y(), initial.top() + minimum.height() - 1))
                self.window.setGeometry(rect)
                return True
            position = self.window.mapFromGlobal(event.globalPosition().toPoint())
            edges = self.edges_at(position)
            horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
            vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
            if horizontal and vertical:
                diagonal = edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
                cursor = Qt.CursorShape.SizeFDiagCursor if diagonal else Qt.CursorShape.SizeBDiagCursor
            elif horizontal:
                cursor = Qt.CursorShape.SizeHorCursor
            elif vertical:
                cursor = Qt.CursorShape.SizeVerCursor
            else:
                cursor = Qt.CursorShape.ArrowCursor
            watched.setCursor(cursor)
            if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton and edges:
                handle = self.window.windowHandle()
                if handle is None or not handle.startSystemResize(edges):
                    self._drag = (edges, event.globalPosition().toPoint(), self.window.geometry())
                return True
        elif kind == QEvent.Type.Leave:
            watched.unsetCursor()
        return super().eventFilter(watched, event)
