"""Per-source, per-operation editable draft. No Qt, filesystem or FFmpeg calls."""
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from uuid import uuid4

from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import MediaOperation
from media_wrapper.domain.remux import Container


class EditScope(str, Enum):
    INCLUDED = 'included'
    SELECTED = 'selected'


class _Mixed(Enum):
    VALUE = 'Mixed'


MIXED = _Mixed.VALUE


@dataclass(frozen=True)
class DraftOptions:
    request: ConversionRequest
    folder: str = ''
    template: str = '{name}_{operation}'
    auto_number: bool = False
    output_override: str = ''
    preset_name: str = ''


def default_options(media: MediaFile, operation: MediaOperation) -> DraftOptions:
    tracks = tuple((s.index, 'copy' if operation == MediaOperation.REMUX else
                    {'video': 'libx264', 'audio': 'aac'}.get(s.kind, 'copy'))
                   for s in media.streams if s.index is not None)
    request = ConversionRequest(media.path.with_name(f'{media.path.stem}_{operation.value}.mkv'),
                                Container.MATROSKA, tracks, operation=operation,
                                mode='quality' if operation == MediaOperation.COMPRESS else 'default')
    return DraftOptions(request)


@dataclass
class DraftItem:
    path: Path
    id: str = field(default_factory=lambda: uuid4().hex)
    included: bool = True
    inspection: InspectionRecord | None = None
    options: dict[MediaOperation, DraftOptions] = field(default_factory=dict)
    queued: dict[MediaOperation, DraftOptions] = field(default_factory=dict)
    revision: int = 0

    @property
    def media(self):
        return self.inspection.media if self.inspection else None

    @property
    def inspected(self):
        return bool(self.inspection and self.inspection.status == InspectionStatus.COMPLETED and self.media)


class DraftState:
    def __init__(self):
        self.items: dict[str, DraftItem] = {}
        self._paths: dict[Path, str] = {}
        self.operation = MediaOperation.REMUX
        self.scope = EditScope.INCLUDED
        self.selected: tuple[str, ...] = ()
        self.revision = 0

    def add(self, paths: tuple[Path, ...]) -> tuple[DraftItem, ...]:
        additions = []
        for path in paths:
            if path not in self._paths:
                item = DraftItem(path)
                self.items[item.id] = item
                self._paths[path] = item.id
                additions.append(item)
        if additions:
            self.revision += 1
        return tuple(additions)

    def remove(self, ids):
        for item_id in ids:
            item = self.items.pop(item_id, None)
            if item:
                self._paths.pop(item.path, None)
        self.selected = tuple(i for i in self.selected if i in self.items)
        self.revision += 1

    def include(self, item_id, included):
        item = self.items[item_id]
        if item.included != included:
            item.included = included
            item.revision += 1
            self.revision += 1

    def inspected(self, record: InspectionRecord):
        item_id = self._paths.get(record.path)
        if item_id is None:
            return  # The source may have been removed while probing.
        item = self.items[item_id]
        item.inspection = record
        if item.inspected and not item.options:
            item.options = {op: default_options(item.media, op) for op in MediaOperation}
        item.revision += 1
        self.revision += 1

    def targets(self) -> tuple[DraftItem, ...]:
        if self.scope == EditScope.SELECTED:
            return tuple(self.items[i] for i in self.selected if i in self.items)
        return tuple(item for item in self.items.values() if item.included)

    def editable(self):
        return tuple(item for item in self.targets() if item.inspected)

    def value(self, name):
        values = [self.field_value(item, name) for item in self.editable()]
        if not values:
            return None
        return values[0] if all(v == values[0] for v in values) else MIXED

    def field_value(self, item, name):
        options = item.options[self.operation]
        if name in ('video_encoder', 'audio_encoder'):
            kind = name.split('_')[0]
            indices = {s.index for s in item.media.streams if s.kind == kind}
            choices = [encoder for index, encoder in options.request.tracks if index in indices and encoder != 'omit']
            if not choices:
                return None
            return choices[0] if len(set(choices)) == 1 else MIXED
        return getattr(options, name) if hasattr(options, name) else getattr(options.request, name)

    def patch(self, name, value, ids=None, *, preset_name=''):
        targets = self.editable() if ids is None else tuple(self.items[i] for i in ids if i in self.items and self.items[i].inspected)
        changed = False
        for item in targets:
            current = item.options[self.operation]
            if name in ('video_encoder', 'audio_encoder'):
                kind = name.split('_')[0]
                indices = {s.index for s in item.media.streams if s.kind == kind}
                tracks = tuple((i, value if i in indices and encoder != 'omit' else encoder)
                               for i, encoder in current.request.tracks)
                updated = replace(current, request=replace(current.request, tracks=tracks), preset_name=preset_name)
            elif name in {'folder', 'template', 'auto_number', 'output_override'}:
                updated = replace(current, **{name: value}, preset_name=preset_name)
            else:
                updated = replace(current, request=replace(current.request, **{name: value}), preset_name=preset_name)
            if updated != current:
                item.options[self.operation] = updated
                item.revision += 1
                changed = True
        if changed:
            self.revision += 1

    def reset(self, ids=None):
        targets = self.editable() if ids is None else tuple(self.items[i] for i in ids if i in self.items and self.items[i].inspected)
        for item in targets:
            item.options[self.operation] = default_options(item.media, self.operation)
            item.revision += 1
        if targets:
            self.revision += 1
