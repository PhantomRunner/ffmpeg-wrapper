"""Workstation design tokens in Qt logical pixels (not physical screen pixels)."""
from types import MappingProxyType

COLORS = MappingProxyType({
    'background': '#151A20', 'panel': '#20262E', 'control': '#272E38',
    'hover': '#323D49', 'border': '#3A444F', 'accent': '#2F84EE',
    'accent_hover': '#62A4F6', 'text': '#F3F6FA', 'secondary': '#B3BDC9',
    'success': '#48C782', 'error': '#F06B70', 'processing': '#8FBFFF',
    'warning': '#F1C04C', 'on_accent': '#071421', 'subtle': '#1A2028',
    'selection': '#234369', 'success_surface': '#203D30',
    'error_surface': '#422A30',
})
BODY_SIZE = 13
CONTROL_HEIGHT = 32
SPACING = 8
PADDING = 12
RADIUS = 8
