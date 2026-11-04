"""Complete studio styling, scoped to the application window and its dialogs."""
from functools import lru_cache
from importlib.resources import files
from string import Template

from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QWidget

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
    resource = files('media_wrapper').joinpath('resources')
    assets = {name: str(resource.joinpath(filename)).replace('\\', '/') for name, filename in (
        ('check_icon', 'check.svg'), ('minus_icon', 'minus.svg'), ('radio_icon', 'radio.svg'),
        ('chevron_down', 'chevron-down.svg'), ('chevron_up', 'chevron-up.svg'),
        ('chevron_right', 'chevron-right.svg'), ('close_icon', 'close.svg'),
    )}
    return Template(source).substitute(**COLORS, **assets, body_size=BODY_SIZE,
                                       control_height=CONTROL_HEIGHT, spacing=SPACING,
                                       padding=PADDING, radius=RADIUS)


def apply_theme(window: QWidget) -> None:
    from media_wrapper.ui.theme.style import StudioStyle

    app = QApplication.instance()
    # Widgets do not own their QStyle. Keep it alive until after Qt destroys
    # their children, including the short-lived static message boxes.
    if not hasattr(app, 'studio_style'):
        app.studio_style = StudioStyle()
        app.studio_style.setParent(app)
    style = app.studio_style
    window.setStyle(style)
    window.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
    palette = QPalette(window.palette())
    for role, color in ((QPalette.ColorRole.Window, 'background'), (QPalette.ColorRole.WindowText, 'text'),
                        (QPalette.ColorRole.Base, 'background'), (QPalette.ColorRole.AlternateBase, 'subtle'),
                        (QPalette.ColorRole.Text, 'text'), (QPalette.ColorRole.Button, 'control'),
                        (QPalette.ColorRole.ButtonText, 'text'), (QPalette.ColorRole.Highlight, 'selection'),
                        (QPalette.ColorRole.HighlightedText, 'text'),
                        (QPalette.ColorRole.ToolTipBase, 'control'), (QPalette.ColorRole.ToolTipText, 'text'),
                        (QPalette.ColorRole.PlaceholderText, 'secondary'),
                        (QPalette.ColorRole.Light, 'hover'), (QPalette.ColorRole.Midlight, 'control'),
                        (QPalette.ColorRole.Mid, 'border'), (QPalette.ColorRole.Dark, 'background'),
                        (QPalette.ColorRole.Shadow, 'background'), (QPalette.ColorRole.Link, 'accent'),
                        (QPalette.ColorRole.LinkVisited, 'processing'), (QPalette.ColorRole.BrightText, 'text')):
        palette.setColor(role, QColor(COLORS[color]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS['secondary']))
    window.setPalette(palette)
    window.setStyleSheet(stylesheet())
