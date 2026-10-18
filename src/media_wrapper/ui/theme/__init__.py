"""A scoped theme: native dialogs and other application windows keep their style."""
from functools import lru_cache
from importlib.resources import files
from string import Template

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget

from media_wrapper.ui.theme.tokens import (
    BODY_SIZE,
    COLORS,
    CONTROL_HEIGHT,
    PADDING,
    RADIUS,
    SPACING,
)


@lru_cache(maxsize=1)
def stylesheet() -> str:
    # Small packaged resource, loaded once; no media I/O or runtime style polling.
    source = files('media_wrapper').joinpath('resources', 'theme.qss').read_text(encoding='utf-8')
    return Template(source).substitute(**COLORS, body_size=BODY_SIZE,
                                       control_height=CONTROL_HEIGHT, spacing=SPACING,
                                       padding=PADDING, radius=RADIUS,
                                       check_icon=str(files('media_wrapper').joinpath('resources', 'check.svg')).replace('\\', '/'))


def apply_theme(window: QWidget) -> None:
    palette = QPalette(window.palette())
    for role, color in ((QPalette.ColorRole.Window, 'background'), (QPalette.ColorRole.WindowText, 'text'),
                        (QPalette.ColorRole.Base, 'panel'), (QPalette.ColorRole.AlternateBase, 'control'),
                        (QPalette.ColorRole.Text, 'text'), (QPalette.ColorRole.Button, 'control'),
                        (QPalette.ColorRole.ButtonText, 'text'), (QPalette.ColorRole.Highlight, 'accent'),
                        (QPalette.ColorRole.HighlightedText, 'on_accent'),
                        (QPalette.ColorRole.ToolTipBase, 'control'), (QPalette.ColorRole.ToolTipText, 'text'),
                        (QPalette.ColorRole.PlaceholderText, 'secondary')):
        palette.setColor(role, QColor(COLORS[color]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS['secondary']))
    window.setPalette(palette)
    window.setStyleSheet(stylesheet())
