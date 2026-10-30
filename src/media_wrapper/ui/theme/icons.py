"""Small, consistent vector icons; independent of platform icon themes."""
from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from media_wrapper.ui.theme.tokens import COLORS

_PATHS = {
    'media': '<rect x="3" y="3" width="18" height="18" rx="5"/><path d="m10 8 6 4-6 4Z"/>',
    'play': '<path d="m8 5 11 7-11 7Z"/>',
    'pause': '<path d="M8 5v14M16 5v14"/>',
    'import': '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/>',
    'download': '<path d="M12 3v13m-5-5 5 5 5-5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    'inspect': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5M8 10.5h5m-2.5-2.5v5"/>',
    'remux': '<rect x="3" y="4" width="7" height="16" rx="2"/><rect x="14" y="4" width="7" height="16" rx="2"/><path d="M7 12h10m-3-3 3 3-3 3"/>',
    'convert': '<path d="M4 8h15m-4-4 4 4-4 4M20 16H5m4-4-4 4 4 4"/>',
    'compress': '<path d="M4 4l6 6M4 9V4h5m11 0-6 6m1-6h5v5M4 20l6-6m-6 1v5h5m11 0-6-6m1 6h5v-5"/>',
    'queue': '<rect x="4" y="4" width="16" height="5" rx="2"/><path d="M4 13h16M4 18h11m3-2 3 3-3 3"/>',
    'settings': '<path d="m10 3-.6 2.3-2 .9-2.1-.6-2 3.4 1.6 1.7v2.6L3.3 15l2 3.4 2.1-.6 2 .9L10 21h4l.6-2.3 2-.9 2.1.6 2-3.4-1.6-1.7v-2.6L20.7 9l-2-3.4-2.1.6-2-.9L14 3Z"/><circle cx="12" cy="12" r="3"/>',
    'reset': '<path d="M4 10a8 8 0 1 1 1 7M4 4v6h6"/>',
    'layout': '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18M9 9v11"/>',
    'close': '<path d="m6 6 12 12M6 18 18 6"/>',
    'minimize': '<path d="M5 12h14"/>',
    'maximize': '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    'restore': '<rect x="4" y="8" width="12" height="12" rx="2"/><path d="M8 8V4h12v12h-4"/>',
    'folder': '<path d="M3 7V5a1 1 0 0 1 1-1h5l3 3h8a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Zm0 3h18"/>',
    'file': '<path d="M14 3H5v18h14V8Zm0 0v5h5M8 12h8m-8 4h6"/>',
    'video': '<rect x="3" y="5" width="13" height="14" rx="3"/><path d="m16 10 5-3v10l-5-3"/>',
    'audio': '<path d="M9 18V5l11-2v13M9 9l11-2"/><ellipse cx="6" cy="18" rx="3" ry="3"/><ellipse cx="17" cy="16" rx="3" ry="3"/>',
    'subtitles': '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M6 12h3m3 0h6M6 15h6m3 0h3"/>',
    'trash': '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'check': '<path d="m5 12 4 4L19 6"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>',
    'warning': '<path d="M10.3 4 2 19a1 1 0 0 0 1 2h18a1 1 0 0 0 1-2L13.7 4a2 2 0 0 0-3.4 0ZM12 9v4m0 4v.1"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'chevron-up': '<path d="m6 15 6-6 6 6"/>',
    'chevron-right': '<path d="m9 6 6 6-6 6"/>',
    'chevron-left': '<path d="m15 6-6 6 6 6"/>',
}
_ALIASES = {'upload': 'import', 'search': 'inspect', 'refresh': 'reset', 'film': 'media'}


@lru_cache(maxsize=192)
def icon(name: str, size: int = 16, color: str | None = None) -> QIcon:
    """Render both normal and disabled states at common display densities."""
    path = _PATHS[_ALIASES.get(name, name)]
    result = QIcon()
    for mode, stroke in ((QIcon.Mode.Normal, color or COLORS['text']),
                         (QIcon.Mode.Selected, color or COLORS['accent']),
                         (QIcon.Mode.Disabled, COLORS['secondary'])):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
               f'fill="none" stroke="{stroke}" stroke-width="1.7" '
               f'stroke-linecap="round" stroke-linejoin="round">{path}</svg>')
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        for scale in (1, 2, 3):
            pixmap = QPixmap(size * scale, size * scale)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            pixmap.setDevicePixelRatio(scale)
            result.addPixmap(pixmap, mode)
    return result
