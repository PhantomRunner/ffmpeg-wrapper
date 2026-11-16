"""Independent output configurations for inspected media sources."""
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from uuid import uuid4

from media_wrapper.domain.capabilities import GPU_ENCODERS
from media_wrapper.domain.conversion import ConversionRequest
from media_wrapper.domain.inspection import InspectionRecord, InspectionStatus
from media_wrapper.domain.media import MediaFile
from media_wrapper.domain.operations import MediaOperation
from media_wrapper.domain.remux import Container


class EditScope(str, Enum):
    ACTIVE = 'active'
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
    preset_modified: bool = False


def default_options(media: MediaFile, operation: MediaOperation) -> DraftOptions:
    tracks = tuple((s.index, 'copy' if operation == MediaOperation.REMUX else
                    {'video': 'libx264', 'audio': 'aac'}.get(s.kind, 'copy'))
                   for s in media.streams if s.index is not None)
    request = ConversionRequest(media.path.with_name(f'{media.path.stem}_{operation.value}.mkv'),
                                Container.MATROSKA, tracks, operation=operation,
                                mode='quality' if operation == MediaOperation.COMPRESS else 'default',
                                target_size_bytes=104857600 if operation != MediaOperation.REMUX else None)
    return DraftOptions(request)


@dataclass
class DraftItem:
    path: Path
    id: str = field(default_factory=lambda: uuid4().hex)
    included: bool = True
    inspection: InspectionRecord | None = None
    options: dict[MediaOperation, DraftOptions] = field(default_factory=dict)
    defaults: dict[MediaOperation, DraftOptions] = field(default_factory=dict)
    queued: dict[MediaOperation, DraftOptions] = field(default_factory=dict)
    revision: int = 0
    fingerprint: tuple[int, int] | None = None
    output_ids: list[str] = field(default_factory=list)
    next_output_number: int = 1

    @property
    def media(self):
        return self.inspection.media if self.inspection else None

    @property
    def inspected(self):
        return bool(self.inspection and self.inspection.status == InspectionStatus.COMPLETED and self.media)


@dataclass
class DraftOutput:
    source_id: str
    label: str
    operation: MediaOperation
    id: str = field(default_factory=lambda: uuid4().hex)
    included: bool = True
    options: dict[MediaOperation, DraftOptions] = field(default_factory=dict)
    defaults: dict[MediaOperation, DraftOptions] = field(default_factory=dict)
    queued: dict[MediaOperation, DraftOptions] = field(default_factory=dict)
    revision: int = 0
    number: int = 1


class DraftState:
    def __init__(self, *, multiple_outputs=False):
        self.items: dict[str, DraftItem] = {}
        self.outputs: dict[str, DraftOutput] = {}
        self._paths: dict[Path, str] = {}
        self.multiple_outputs = multiple_outputs
        self._operation = MediaOperation.REMUX
        self.scope = EditScope.ACTIVE if multiple_outputs else EditScope.INCLUDED
        self.selected: tuple[str, ...] = ()
        self.selected_outputs: tuple[str, ...] = ()
        self.active_output_id: str | None = None
        self.inspector_source_id: str | None = None
        self.revision = 0

    @property
    def operation(self):
        return self._operation

    @operation.setter
    def operation(self, operation):
        self.set_operation(operation)

    def set_operation(self, operation):
        self._operation = operation
        if not self.multiple_outputs:
            return
        for output in self.output_targets():
            if output.operation != operation:
                output.operation = operation
                output.revision += 1
                self.revision += 1

    def focus_output(self, output_id):
        output = self.outputs.get(output_id)
        self.active_output_id = output.id if output else None
        if output:
            self._operation = output.operation

    def outputs_for(self, source_id):
        item = self.items.get(source_id)
        return tuple(self.outputs[output_id] for output_id in item.output_ids) if item else ()

    def add_output(self, source_id, label='', operation=None):
        item = self.items[source_id]
        number = item.next_output_number
        item.next_output_number += 1
        output = DraftOutput(source_id, label.strip() or f'Output {number}',
                             operation or self._operation, number=number)
        if not item.output_ids:
            output.included = item.included
            output.options, output.defaults, output.queued = item.options, item.defaults, item.queued
        elif item.inspected:
            self._initialize_output(item, output)
        item.output_ids.append(output.id)
        self.outputs[output.id] = output
        if self.active_output_id is None:
            self.focus_output(output.id)
        item.included = True if output.included else item.included
        self.revision += 1
        return output

    def remove_output(self, output_id):
        output = self.outputs[output_id]
        item = self.items[output.source_id]
        if len(item.output_ids) == 1:
            raise ValueError('Keep at least one output per source or remove the source.')
        item.output_ids.remove(output_id)
        self.outputs.pop(output_id)
        primary = self.outputs[item.output_ids[0]]
        item.options, item.defaults, item.queued = primary.options, primary.defaults, primary.queued
        item.included = any(child.included for child in self.outputs_for(item.id))
        self._clean_selection()
        self.revision += 1

    def rename_output(self, output_id, label):
        label = label.strip()
        if not label:
            raise ValueError('Enter a name for this output.')
        self.outputs[output_id].label = label

    def reuse_plan(self, plan, *, label='Reuse', fingerprint=None):
        path = plan.media.path
        source_id = self._paths.get(path)
        if source_id is None:
            item, = self.add((path,))
            self.inspected(InspectionRecord(path, InspectionStatus.COMPLETED, plan.media))
            item.fingerprint = fingerprint
            output = self.outputs[item.output_ids[0]]
            output.label = label
        else:
            item = self.items[source_id]
            if not item.inspected:
                raise ValueError('Inspect this source before reusing a configuration.')
            if fingerprint and item.fingerprint and fingerprint != item.fingerprint:
                raise ValueError('The source has changed since that attempt. Configure a fresh output.')
            output = self.add_output(source_id, label, plan.operation)
        output.operation = plan.operation
        options = output.options[plan.operation]
        profiles = {stream.index: stream.profile for stream in plan.streams}
        tracks = tuple((stream.index, profiles[stream.index].encoder if stream.index in profiles else 'omit')
                       for stream in item.media.streams if stream.index is not None)
        order = tuple(profiles)
        hardware = next((entry.encoder for entry in profiles.values() if entry.encoder in GPU_ENCODERS), None)
        request = replace(
            options.request, container=plan.output.container, tracks=tracks, track_order=order,
            stream_profiles=tuple((index, profile) for index, profile in profiles.items() if profile.encoder != 'copy'),
            target_size_bytes=plan.target_size_bytes, mode='target' if plan.target_size_bytes else 'default',
            hardware_mode='GPU' if hardware else 'CPU', gpu_encoder=hardware or 'auto',
            metadata_policy=plan.metadata_policy, chapter_policy=plan.chapter_policy, deep_verify=plan.deep_verify,
            custom_arguments=' '.join(part for option in plan.custom_options for part in option),
        )
        output.options[plan.operation] = replace(
            options, request=request, folder=str(plan.output.path.parent),
            template=f'{{name}}_{{operation}}_{output.number}', auto_number=True,
        )
        output.revision += 1
        self.revision += 1
        return output

    def include_output(self, output_id, included):
        output = self.outputs[output_id]
        if output.included == included:
            return
        output.included = included
        output.revision += 1
        item = self.items[output.source_id]
        item.included = any(child.included for child in self.outputs_for(item.id))
        item.revision += 1
        self.revision += 1

    def _clean_selection(self):
        self.selected = tuple(i for i in self.selected if i in self.items)
        self.selected_outputs = tuple(i for i in self.selected_outputs if i in self.outputs)
        if self.active_output_id not in self.outputs:
            self.focus_output(next(iter(self.outputs), None))
        if self.inspector_source_id not in self.items:
            self.inspector_source_id = None

    def _initialize_output(self, item, output):
        for operation in MediaOperation:
            options = item.defaults.get(operation) or default_options(item.media, operation)
            if output.number > 1:
                template = options.template
                suffix = f'_{output.number}'
                template = template.replace('{ext}', f'{suffix}{{ext}}') if '{ext}' in template else template + suffix
                options = replace(options, template=template, output_override='')
            output.options[operation] = output.defaults[operation] = options

    def add(self, paths: tuple[Path, ...]) -> tuple[DraftItem, ...]:
        additions = []
        for path in paths:
            if path not in self._paths:
                item = DraftItem(path)
                self.items[item.id] = item
                self._paths[path] = item.id
                additions.append(item)
                self.add_output(item.id)
        return tuple(additions)

    def remove(self, ids):
        for item_id in ids:
            item = self.items.pop(item_id, None)
            if item:
                self._paths.pop(item.path, None)
                for output_id in item.output_ids:
                    self.outputs.pop(output_id)
        self._clean_selection()
        self.revision += 1

    def include(self, item_id, included):
        item = self.items[item_id]
        for output in self.outputs_for(item.id):
            self.include_output(output.id, included)

    def inspected(self, record: InspectionRecord):
        item_id = self._paths.get(record.path)
        if item_id is None:
            return  # The source may have been removed while probing.
        item = self.items[item_id]
        item.inspection = record
        if item.inspected:
            for output in self.outputs_for(item_id):
                if not output.options:
                    self._initialize_output(item, output)
        item.revision += 1
        self.revision += 1

    def targets(self) -> tuple[DraftItem, ...]:
        if self.multiple_outputs:
            source_ids = dict.fromkeys(output.source_id for output in self.output_targets())
            return tuple(self.items[source_id] for source_id in source_ids)
        if self.scope == EditScope.SELECTED:
            return tuple(self.items[i] for i in self.selected if i in self.items)
        return tuple(item for item in self.items.values() if item.included)

    def editable(self):
        return tuple(item for item in self.targets() if item.inspected)

    def output_targets(self):
        if self.scope == EditScope.ACTIVE:
            output = self.outputs.get(self.active_output_id)
            return (output,) if output else ()
        if self.scope == EditScope.SELECTED:
            ids = self.selected_outputs or tuple(
                output.id for source_id in self.selected for output in self.outputs_for(source_id))
            return tuple(self.outputs[output_id] for output_id in dict.fromkeys(ids)
                         if output_id in self.outputs)
        return tuple(output for output in self.outputs.values() if output.included)

    def editable_outputs(self):
        return tuple(output for output in self.output_targets() if self.items[output.source_id].inspected)

    def _configurations(self, ids=None):
        if not self.multiple_outputs:
            return self.editable() if ids is None else tuple(
                self.items[i] for i in ids if i in self.items and self.items[i].inspected)
        if ids is None:
            return self.editable_outputs()
        outputs = dict.fromkeys(output.id for i in ids for output in
                                ((self.outputs[i],) if i in self.outputs else self.outputs_for(i)))
        return tuple(self.outputs[i] for i in outputs if self.items[self.outputs[i].source_id].inspected)

    def value(self, name):
        values = [self.field_value(target, name) for target in self._configurations()]
        if name in ('video_encoder', 'audio_encoder'):
            values = [value for value in values if value is not None]
        if not values:
            return None
        return values[0] if all(v == values[0] for v in values) else MIXED

    def field_value(self, target, name):
        item, operation = self._source_operation(target)
        options = target.options[operation]
        if name in ('video_encoder', 'audio_encoder'):
            kind = name.split('_')[0]
            indices = {s.index for s in item.media.streams if s.kind == kind}
            choices = [encoder for index, encoder in options.request.tracks if index in indices and encoder != 'omit']
            if not choices:
                return None
            return choices[0] if len(set(choices)) == 1 else MIXED
        return getattr(options, name) if hasattr(options, name) else getattr(options.request, name)

    def _source_operation(self, target):
        if isinstance(target, DraftOutput):
            return self.items[target.source_id], target.operation
        return target, self.operation

    def patch(self, name, value, ids=None, *, preset_name=''):
        changed = False
        for target in self._configurations(ids):
            item, operation = self._source_operation(target)
            current = target.options[operation]
            label = preset_name or current.preset_name
            modified = bool(current.preset_name and not preset_name)
            if name in ('video_encoder', 'audio_encoder'):
                kind = name.split('_')[0]
                indices = {s.index for s in item.media.streams if s.kind == kind}
                tracks = tuple((i, value if i in indices and encoder != 'omit' else encoder)
                               for i, encoder in current.request.tracks)
                updated = replace(current, request=replace(current.request, tracks=tracks), preset_name=label, preset_modified=modified)
            elif name in {'folder', 'template', 'auto_number', 'output_override'}:
                updated = replace(current, **{name: value}, preset_name=label, preset_modified=modified)
            else:
                updated = replace(current, request=replace(current.request, **{name: value}), preset_name=label, preset_modified=modified)
            if updated != current:
                target.options[operation] = updated
                target.revision += 1
                changed = True
        if changed:
            self.revision += 1

    def reset(self, ids=None):
        targets = self._configurations(ids)
        for target in targets:
            item, operation = self._source_operation(target)
            target.options[operation] = target.defaults.get(operation) or default_options(item.media, operation)
            target.revision += 1
        if targets:
            self.revision += 1
