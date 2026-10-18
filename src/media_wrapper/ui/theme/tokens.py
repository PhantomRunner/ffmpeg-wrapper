"""Workstation design tokens in Qt logical pixels (not physical screen pixels)."""
from types import MappingProxyType

COLORS = MappingProxyType({
    'background': '#15171C', 'panel': '#22242B', 'control': '#30333C',
    'hover': '#3B3F4B', 'border': '#505562', 'accent': '#A99CF5',
    'accent_hover': '#BDB2FF', 'text': '#ECECF1', 'secondary': '#A3A6B2',
    'success': '#419883', 'error': '#D46B76', 'processing': '#8C79D7',
    'on_accent': '#15171C',
})
BODY_SIZE = 13
CONTROL_HEIGHT = 32
SPACING = 8
PADDING = 12
RADIUS = 6
