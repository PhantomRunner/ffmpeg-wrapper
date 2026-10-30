"""Workstation design tokens in Qt logical pixels (not physical screen pixels)."""
from types import MappingProxyType

COLORS = MappingProxyType({
    'background': '#111213', 'panel': '#1A1B1E', 'control': '#27282C',
    'hover': '#343439', 'border': '#45464D', 'accent': '#F2B45F',
    'accent_hover': '#FFCB86', 'text': '#F3F0EB', 'secondary': '#B7B2AA',
    'success': '#9DCCA9', 'error': '#F09A94', 'processing': '#D69A4E',
    'on_accent': '#24190C', 'subtle': '#202125', 'selection': '#403323',
    'success_surface': '#25352A', 'error_surface': '#3C2828',
})
BODY_SIZE = 13
CONTROL_HEIGHT = 32
SPACING = 8
PADDING = 12
RADIUS = 8
