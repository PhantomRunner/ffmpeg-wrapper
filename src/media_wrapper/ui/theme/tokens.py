"""Workstation design tokens in Qt logical pixels (not physical screen pixels)."""
from types import MappingProxyType

COLORS = MappingProxyType({
    'background': '#1B1B20', 'panel': '#232327', 'control': '#2B2A30',
    'hover': '#38373F', 'border': '#53515D', 'accent': '#B9B1FF',
    'accent_hover': '#CCC6FF', 'text': '#F3F1F7', 'secondary': '#C5C1CE',
    'success': '#78D5A0', 'error': '#FF9D9F', 'processing': '#A6CAFF',
    'warning': '#F6CB6A', 'on_accent': '#071421', 'subtle': '#202025',
    'selection': '#41405B', 'success_surface': '#273E32',
    'error_surface': '#4B2D32',
})
LIGHT_COLORS = MappingProxyType({
    'background': '#F9F8FC', 'panel': '#FFFFFF', 'control': '#F0EFF5',
    'hover': '#E6E3F0', 'border': '#938DA3', 'accent': '#514291',
    'accent_hover': '#463981', 'text': '#22202A', 'secondary': '#514E5D',
    'success': '#21673F', 'error': '#9E293B', 'processing': '#1F5198',
    'warning': '#755000', 'on_accent': '#FFFFFF', 'subtle': '#F5F4F8',
    'selection': '#E3DFFD', 'success_surface': '#E4F2E9',
    'error_surface': '#F9E7E9',
})
BODY_SIZE = 13
CONTROL_HEIGHT = 32
SPACING = 8
PADDING = 12
RADIUS = 5
