"""Pure output-template syntax; filesystem collision policy belongs to services."""
from string import Formatter


def draft_output_name(template, source, operation, index, suffix):
    if not template or len(template) > 256:
        raise ValueError('Supply a filename template of at most 256 characters.')
    for _, field, spec, conversion in Formatter().parse(template):
        if field is not None and (field not in {'name', 'stem', 'operation', 'index', 'ext'} or spec or conversion):
            raise ValueError('Use only {name}, {stem}, {operation}, {index}, {ext}; no format expressions.')
    name = template.format(name=source.stem, stem=source.stem, operation=operation.value, index=index, ext=suffix)
    if not name or '/' in name or '\\' in name or name in ('.', '..'):
        raise ValueError('The template must produce a filename, not a path.')
    if not name.lower().endswith(suffix):
        if '{ext}' in template:
            raise ValueError('Put {ext} at the end of the filename template.')
        name += suffix
    return name
